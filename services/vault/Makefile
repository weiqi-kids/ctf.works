# vault — A/D CTF 漏洞服務(pwn,C daemon)
# 用 -O0 編譯,讓 OOB read 漏洞行為穩定可重複(不被最佳化改寫記憶體佈局)。

CC      ?= gcc
CFLAGS  ?= -O0 -g -Wall -Wextra -std=c11 -fno-stack-protector
TARGET   = vault
SRC      = vault.c

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC)

run: $(TARGET)
	./$(TARGET)

clean:
	rm -f $(TARGET)
