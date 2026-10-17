# FILMLAB firmware build (WSL2, clang - 需与 fpSup 构建环境相同的工具链)
# 产物: boot.o monitor.o gen_looks.o → firmware.elf → 各段抽出到 ../dist/LOOKS.BIN

CC      = clang
TARGET  = armv7a-none-eabi
CFLAGS  = -target $(TARGET) -O1 -ffreestanding -nostdlib -mfloat-abi=soft \
          -fno-builtin -fno-stack-protector -Wall
ASFLAGS = -target $(TARGET)

OBJS = boot.o monitor.o gen_looks.o

all: firmware.elf sections.txt

%.o: %.S
	$(CC) $(ASFLAGS) -c -o $@ $<

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

gen_looks.c: ../tools/gen_looks.py ../tools/looks.cfg
	python3 ../tools/gen_looks.py $@

firmware.elf: $(OBJS)
	$(CC) $(CFLAGS) -T link.ld -o $@ $(OBJS)

sections.txt: firmware.elf
	$(TARGET)-objdump -h $< > $@ || llvm-objdump -h $< > $@

clean:
	rm -f *.o firmware.elf sections.txt gen_looks.c
