/*
 * vault.c — A/D CTF 漏洞服務(pwn,C daemon,port 10000)
 *
 * 協定:line-based TCP,每行以 '\n' 結尾,ASCII。照 CONTRACTS.md §2.3。
 *   REGISTER <user>          -> OK <token>     (配一個 slot,回 token;冪等)
 *   AUTH <user> <token>      -> OK / ERR       (驗證後 session 綁定 my_slot)
 *   SET <secret>             -> OK             (需 AUTH;存進 secrets[my_slot])
 *   GET <idx>                -> SECRET <data>  (需 AUTH;**故意漏洞**:idx 不檢查邊界)
 *   PING                     -> PONG
 *
 * slot/token 方案(checker 可重現,見 README.md):
 *   - slot:由 user 經 FNV-1a 雜湊 mod N,碰撞時線性探測 → 對同 user 穩定。
 *   - token:由 user 經帶固定金鑰的 FNV-1a 導出,輸出成 16 進位字串 → 對同 user 穩定。
 *   兩者皆為使用者字串的決定性函數,故重啟後同 user 仍得到相同 slot/token,
 *   且 checker 可由 flag_id 導出 user 後自行算出 token、預期 slot。
 *
 * 漏洞:GET 處理時,idx 來自使用者輸入且未檢查 0 <= idx < N,
 *   直接 secrets[idx] 讀取 → 可讀到他人 slot 的 secret(OOB / 跨 slot read)。
 *
 * 編譯:gcc -O0(見 Makefile),讓漏洞行為穩定可重複。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/mman.h>

#define PORT        10000
#define N           256        /* secrets 全域陣列大小(slot 數) */
#define SECRET_LEN  256        /* 每個 slot 可存的 secret 最大長度 */
#define USER_LEN    64         /* user 字串上限 */
#define TOKEN_LEN   17         /* token 16 hex 字元 + '\0' */
#define LINE_MAX    1024       /* 單行輸入緩衝上限 */

/*
 * 全域固定大小陣列。為了讓 fork 出的各連線子行程共享同一份狀態
 * (userA 在連線 1 SET 的 secret,userB 在連線 2 GET 才讀得到),
 * 這些陣列放在共享記憶體(mmap MAP_SHARED),由 main() 於 fork 前配置。
 * 仍是「固定大小全域陣列」語意:大小編譯期決定,索引方式不變。
 */
struct shared {
    char  secrets[N][SECRET_LEN];   /* 每個 slot 一段 secret。漏洞讀取的目標。 */
    int   slot_used[N];             /* slot 是否已被某 user 佔用(冪等/碰撞探測) */
    char  slot_user[N][USER_LEN];   /* slot 對應的 user 名稱(冪等比對) */
};
static struct shared *G;            /* 指向共享記憶體 */
#define secrets   (G->secrets)
#define slot_used (G->slot_used)
#define slot_user (G->slot_user)

/* token 導出用的固定金鑰種子。checker 端須用相同常數重現 token。 */
#define TOKEN_SEED  0x9e3779b97f4a7c15ULL

/*
 * FNV-1a 64 位元雜湊。給定 seed 與字串,回傳雜湊值。
 * seed 不同即得到不同雜湊用途(slot 與 token 用不同 seed)。
 */
static unsigned long long fnv1a(unsigned long long seed, const char *s)
{
    unsigned long long h = seed;
    while (*s) {
        h ^= (unsigned char)(*s++);
        h *= 0x100000001b3ULL;   /* FNV prime */
    }
    return h;
}

/*
 * 由 user 決定性導出 token:帶 TOKEN_SEED 的 FNV-1a,取低 64 位輸出成
 * 16 個 16 進位字元。對同 user 永遠相同。
 */
static void derive_token(const char *user, char *out /* >= TOKEN_LEN */)
{
    unsigned long long h = fnv1a(TOKEN_SEED, user);
    static const char hex[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 16; i++) {
        out[15 - i] = hex[h & 0xf];
        h >>= 4;
    }
    out[16] = '\0';
}

/*
 * 由 user 決定性配發 slot。
 * 基底位置 = FNV-1a(user) mod N;若該 slot 已被「別的 user」佔用則線性探測。
 * REGISTER 冪等:同 user 再次呼叫會找到自己原本的 slot 並回傳。
 * 回傳 slot index;若整個表滿了(理論上 N 個 user)回 -1。
 */
static int assign_slot(const char *user)
{
    unsigned long long base = fnv1a(0xcbf29ce484222325ULL, user);
    int start = (int)(base % (unsigned long long)N);
    int i;
    for (i = 0; i < N; i++) {
        int idx = (start + i) % N;
        if (!slot_used[idx]) {
            /* 空位:配給此 user */
            slot_used[idx] = 1;
            strncpy(slot_user[idx], user, USER_LEN - 1);
            slot_user[idx][USER_LEN - 1] = '\0';
            return idx;
        }
        if (strncmp(slot_user[idx], user, USER_LEN) == 0) {
            /* 同 user 已註冊:冪等回傳原 slot */
            return idx;
        }
    }
    return -1;   /* 表滿 */
}

/* 寫出一整段資料(處理短寫) */
static void write_all(int fd, const char *buf, size_t len)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, buf + off, len - off);
        if (n <= 0) {
            if (errno == EINTR) continue;
            return;   /* 對端斷線,放棄 */
        }
        off += (size_t)n;
    }
}

/* 方便用:寫出一個 C 字串 */
static void send_str(int fd, const char *s)
{
    write_all(fd, s, strlen(s));
}

/*
 * 一次讀一行(到 '\n' 為止,不含 '\n' 存入 buf)。
 * 回傳行長度(>=0),或 -1 表連線結束/錯誤。
 * 超過 cap-1 的部分會被截斷(行尾仍讀到 '\n' 為止以保持協定同步)。
 */
static int read_line(int fd, char *buf, int cap)
{
    int len = 0;
    char c;
    for (;;) {
        ssize_t n = read(fd, &c, 1);
        if (n == 0) return len > 0 ? len : -1;   /* EOF */
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (c == '\n') {
            buf[len] = '\0';
            return len;
        }
        if (c == '\r') continue;                 /* 容忍 CRLF */
        if (len < cap - 1) buf[len++] = c;       /* 滿了就丟,但繼續吃到換行 */
    }
}

/*
 * 處理單一連線的 session。
 * session 狀態:authed(是否已 AUTH)、my_slot(目前綁定的 slot)。
 */
static void handle_session(int fd)
{
    char line[LINE_MAX];
    int authed = 0;
    int my_slot = -1;

    for (;;) {
        int len = read_line(fd, line, sizeof(line));
        if (len < 0) break;          /* 連線結束 */
        if (len == 0) continue;      /* 空行,忽略 */

        /* 拆出指令動詞(第一個空白前) */
        char *sp = strchr(line, ' ');
        char *arg = NULL;
        if (sp) {
            *sp = '\0';
            arg = sp + 1;            /* 其餘為參數(可能含空白) */
        }

        if (strcmp(line, "PING") == 0) {
            send_str(fd, "PONG\n");

        } else if (strcmp(line, "REGISTER") == 0) {
            /* REGISTER <user> */
            if (!arg || *arg == '\0') {
                send_str(fd, "ERR\n");
                continue;
            }
            /* user 取到第一個空白或行尾(REGISTER 的 user 不含空白) */
            char *sp2 = strchr(arg, ' ');
            if (sp2) *sp2 = '\0';
            if (strlen(arg) >= USER_LEN) {
                send_str(fd, "ERR\n");
                continue;
            }
            int slot = assign_slot(arg);
            if (slot < 0) {
                send_str(fd, "ERR\n");
                continue;
            }
            char token[TOKEN_LEN];
            derive_token(arg, token);
            char out[128];
            snprintf(out, sizeof(out), "OK %s\n", token);
            send_str(fd, out);

        } else if (strcmp(line, "AUTH") == 0) {
            /* AUTH <user> <token> */
            if (!arg) { send_str(fd, "ERR\n"); continue; }
            char *sp2 = strchr(arg, ' ');
            if (!sp2) { send_str(fd, "ERR\n"); continue; }
            *sp2 = '\0';
            char *user = arg;
            char *tok = sp2 + 1;
            /* token 取到行尾或下一個空白 */
            char *sp3 = strchr(tok, ' ');
            if (sp3) *sp3 = '\0';
            if (strlen(user) >= USER_LEN) { send_str(fd, "ERR\n"); continue; }

            char expect[TOKEN_LEN];
            derive_token(user, expect);
            if (strcmp(tok, expect) == 0) {
                int slot = assign_slot(user);   /* 確保 slot 存在並取得之 */
                if (slot < 0) { send_str(fd, "ERR\n"); continue; }
                authed = 1;
                my_slot = slot;
                send_str(fd, "OK\n");
            } else {
                send_str(fd, "ERR\n");
            }

        } else if (strcmp(line, "SET") == 0) {
            /* SET <secret>(需 AUTH),存進 secrets[my_slot] */
            if (!authed) { send_str(fd, "ERR\n"); continue; }
            const char *secret = arg ? arg : "";
            /* 存進自己的 slot,長度受 SECRET_LEN 限制 */
            strncpy(secrets[my_slot], secret, SECRET_LEN - 1);
            secrets[my_slot][SECRET_LEN - 1] = '\0';
            send_str(fd, "OK\n");

        } else if (strcmp(line, "GET") == 0) {
            /* GET <idx>(需 AUTH)-> SECRET <data> */
            if (!authed) { send_str(fd, "ERR\n"); continue; }
            if (!arg) { send_str(fd, "ERR\n"); continue; }
            int idx = atoi(arg);
            /*
             * ======================= 漏洞點(OOB read) =======================
             * idx 直接來自使用者,且未檢查 0 <= idx < N。
             * 因此 GET <別人的 slot> 會讀到他人 secret(跨 slot read);
             * 極端的 idx(負數/超大)更會越界讀到陣列外記憶體。
             * 安全堵法:在此加上 (idx == my_slot) 或至少 (0 <= idx < N) 檢查。
             */
            char out[SECRET_LEN + 16];
            snprintf(out, sizeof(out), "SECRET %s\n", secrets[idx]);
            /* ================================================================ */
            send_str(fd, out);

        } else {
            send_str(fd, "ERR\n");
        }
    }
}

int main(void)
{
    int srv;
    struct sockaddr_in addr;
    int opt = 1;

    /* 子行程結束自動回收,避免殭屍 */
    signal(SIGCHLD, SIG_IGN);
    /* 寫入已斷線 socket 不要讓整個 daemon 收 SIGPIPE 而死 */
    signal(SIGPIPE, SIG_IGN);

    /* 行緩衝關閉,確保日誌即時輸出 */
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    /* 配置共享記憶體存放全域 secrets 陣列,讓所有連線子行程共用同一份狀態 */
    G = mmap(NULL, sizeof(struct shared), PROT_READ | PROT_WRITE,
             MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (G == MAP_FAILED) { perror("mmap"); return 1; }
    memset(G, 0, sizeof(struct shared));

    srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0) { perror("socket"); return 1; }

    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(PORT);

    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind"); return 1;
    }
    if (listen(srv, 64) < 0) {
        perror("listen"); return 1;
    }

    fprintf(stderr, "[vault] listening on :%d (N=%d slots)\n", PORT, N);

    /* 每連線 fork 一個子行程處理(簡單可靠)。全域 secrets/slot_* 放在
     * 共享記憶體(G,mmap MAP_SHARED),故各連線子行程看到同一份狀態:
     * userA 在某連線 SET 的 secret,userB 另開連線即可 GET 讀到。
     * 多行程同時寫入同一 slot 在本工坊情境下不致衝突(checker/exploit
     * 各用不同 slot),故未加鎖以保持簡單。 */
    for (;;) {
        int cli = accept(srv, NULL, NULL);
        if (cli < 0) {
            if (errno == EINTR) continue;
            perror("accept");
            continue;
        }
        pid_t pid = fork();
        if (pid == 0) {
            /* 子行程 */
            close(srv);
            handle_session(cli);
            close(cli);
            _exit(0);
        }
        /* 父行程 */
        close(cli);
    }
    return 0;
}
