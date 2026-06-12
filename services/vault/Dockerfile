# vault — A/D CTF 漏洞服務(pwn,C daemon,port 10000)
# 兩階段:builder 編譯,runtime 以低權限使用者執行。
#
# 警告:此映像故意內含 OOB read 漏洞,僅供隔離網段內攻防鍛造,切勿公開部署。

# ---- builder ----
FROM gcc:13 AS builder
WORKDIR /src
COPY vault.c Makefile ./
# 用 -O0 編譯讓漏洞穩定(見 Makefile)
RUN make

# ---- runtime ----
FROM debian:bookworm-slim
# 建立非 root 低權限使用者
RUN useradd --no-create-home --shell /usr/sbin/nologin vault
COPY --from=builder /src/vault /usr/local/bin/vault
USER vault
EXPOSE 10000
ENTRYPOINT ["/usr/local/bin/vault"]
