/* monitor.c - FILMLAB v11.2 (v9 core + K5-proven 6s name flash)
 */
typedef unsigned char  u8;
typedef unsigned int   u32;
typedef unsigned short u16;
typedef signed char    i8;
typedef void (*fn_u32)(u32);

#define MODE_MASTER   (*(volatile u8*)0xC31F8914)
#define DLY_TSK       ((fn_u32)0xC03705D8)
#define DRAW_WORD     (*(volatile u32*)0xC0528700)
#define DRAW_PAUSE    0xE12FFF1Eu

#define H_SETMODE     0xC03FE100
#define H_EFF         0xC03FE170
#define H_CON         0xC03FE1F0
#define H_SHP         0xC03FE270
#define H_SAT         0xC03FE2F0
#define H_TON         0xC03FE370
#define H_OSDFILE     0xC03E4270
#define H_OSD         0xC03E3D00

#define POLL_MS       50
#define SETTLE_LOOPS  60
#define BOOT_CHECKS   10
#define BOOT_QUIET    100
#define FLASH_TICKS   40

#define VAR_FIRST     0x18
#define VAR_LAST      0x21
#define N_VARIANTS    (VAR_LAST - VAR_FIRST + 1)

typedef struct { u32 n_addr; u32 addrs[5]; } slot_list_t;
typedef struct { u8 valid; u8 base; u8 menu_idx; u8 name_win;
                 i8 eff,con,shp,sat,ton; u8 name[12]; u8 _p[3];
                 slot_list_t slots; } look_t;
extern const look_t g_looks[N_VARIANTS];

static u8  last_variant = 0;
static u8  active = 0;
static u8  active_base = 0;
static u8  cur_idx = 0;
static u8  settling = 0;
static u8  settle_ctr = 0;
static u8  slot_backup[5][12];
static u8  backup_valid = 0;
static u8  backup_win = 0;
static const slot_list_t *backup_list = 0;

static u16 flash_ticks = 0;
static u8  flash_on_next = 0;
static u16 boot_ticks = 0;
static u32 draw_orig = 0;
static u8  we_paused = 0;

static int quiet_printf(const char *fmt, ...) { return 0; }
typedef void (*handler_t)(u32 *ctx, u32 argc, u32 *argv);
static void call1(u32 handler, const char *arg)
{
    u32 ctx[1];  ctx[0]  = (u32)quiet_printf;
    u32 argv[2]; argv[0] = (u32)arg; argv[1] = 0;
    ((handler_t)handler)(ctx, 1, argv);
}
static void itoa_dec(int v, char *out)
{
    char tmp[6]; int n = 0; unsigned u;
    char *p = out;
    if (v < 0) { *p++ = '-'; u = (unsigned)(-v); } else u = (unsigned)v;
    do { tmp[n++] = (char)('0' + u % 10); u /= 10; } while (u);
    while (n) *p++ = tmp[--n];
    *p = 0;
}
static int menu_of_enum(u8 enu)
{
    static const struct { u8 e, m; } E2M[] = {
        {0x00,0},{0x03,1},{0x05,2},{0x06,3},{0x07,4},{0x08,5},{0x0A,6},{0x0B,7},
        {0x0C,8},{0x0E,9},{0x0F,10},{0x01,11},{0x24,12},{0x0D,13},{0x09,15},
    };
    for (u32 i = 0; i < sizeof(E2M)/sizeof(E2M[0]); i++)
        if (E2M[i].e == enu) return E2M[i].m;
    return -1;
}

static const char * const PN_PATHS[10] = {
    "\\FILMLAB\\0.BIN","\\FILMLAB\\1.BIN","\\FILMLAB\\2.BIN","\\FILMLAB\\3.BIN",
    "\\FILMLAB\\4.BIN","\\FILMLAB\\5.BIN","\\FILMLAB\\6.BIN","\\FILMLAB\\7.BIN",
    "\\FILMLAB\\8.BIN","\\FILMLAB\\9.BIN",
};
static void draw_strip(u8 id)
{
    static const char blank[] = "\\FILMLAB\\B.BIN";
    u32 ctx[1];  ctx[0] = (u32)quiet_printf;
    u32 argv[6];
    argv[0] = (id <= 9) ? (u32)PN_PATHS[id] : (u32)blank;
    argv[1] = (u32)"0"; argv[2] = (u32)"0";
    argv[3] = (u32)"1024"; argv[4] = (u32)"56"; argv[5] = (u32)"0";
    for (u32 i = 0; i < 3; i++)
        ((handler_t)H_OSDFILE)(ctx, 6, argv);
}
static void osd_present(void)
{
    u32 ctx[1];  ctx[0] = (u32)quiet_printf;
    u32 argv[2]; argv[0] = (u32)"1"; argv[1] = 0;
    for (u32 i = 0; i < 3; i++)
        ((handler_t)H_OSD)(ctx, 1, argv);
}
static void redraw_pause(void)
{
    u32 w = DRAW_WORD;
    if (w != DRAW_PAUSE) { draw_orig = w; we_paused = 1; DRAW_WORD = DRAW_PAUSE; }
}
static void redraw_restore(void)
{
    if (we_paused) {
        if (DRAW_WORD == DRAW_PAUSE) {
            DRAW_WORD = draw_orig; DRAW_WORD = draw_orig; DRAW_WORD = draw_orig;
        }
        we_paused = 0;
    }
}
static void flash_pump(void)
{
    if (!flash_ticks) return;
    --flash_ticks;
    if ((flash_ticks & 3) == 2) {       /* 每 4 拍重画一次(200ms)：抗管线擦除 */
        draw_strip(cur_idx);
        osd_present();
    }
    if (flash_ticks == 0) {
        draw_strip(10);
        osd_present();
        redraw_restore();
    }
}

static void slots_write(const slot_list_t *s, const u8 *name)
{
    u32 len = 0;
    while (name[len]) len++;
    len++;
    for (u32 i = 0; i < s->n_addr && i < 5; i++)
        for (u32 j = 0; j < len; j++)
            *(volatile u8*)(s->addrs[i] + j) = name[j];
}
static void slots_backup(const slot_list_t *s, u8 win)
{
    backup_list = s; backup_win = win;
    for (u32 i = 0; i < s->n_addr && i < 5; i++)
        for (u32 j = 0; j < win && j < 12; j++)
            slot_backup[i][j] = *(volatile u8*)(s->addrs[i] + j);
}
static void slots_restore(void)
{
    if (!backup_valid || !backup_list) return;
    for (u32 i = 0; i < backup_list->n_addr && i < 5; i++)
        for (u32 j = 0; j < backup_win && j < 12; j++)
            *(volatile u8*)(backup_list->addrs[i] + j) = slot_backup[i][j];
}

static void apply_look(const look_t *lk)
{
    if (backup_valid && lk->base != active_base) {
        slots_restore();
        backup_valid = 0;
    }
    if (!backup_valid) {
        slots_backup(&lk->slots, lk->name_win);
        backup_valid = 1;
    }
    active_base = lk->base;
    char buf[8];
    itoa_dec(lk->menu_idx, buf); call1(H_SETMODE, buf);
    itoa_dec(lk->eff, buf); call1(H_EFF, buf);
    itoa_dec(lk->con, buf); call1(H_CON, buf);
    itoa_dec(lk->shp, buf); call1(H_SHP, buf);
    itoa_dec(lk->sat, buf); call1(H_SAT, buf);
    itoa_dec(lk->ton, buf); call1(H_TON, buf);
    slots_write(&lk->slots, lk->name);
    active = 1;
    last_variant = 0;
    if (flash_on_next) {
        flash_on_next = 0;
        if (boot_ticks >= BOOT_QUIET) {
            redraw_pause();
            draw_strip(cur_idx);
            osd_present();
            flash_ticks = FLASH_TICKS;
        }
    }
}

static void exit_look(void)
{
    char buf[8];
    if (flash_ticks) { draw_strip(10); osd_present(); redraw_restore(); flash_ticks = 0; }
    slots_restore();
    int cur_menu  = menu_of_enum(MODE_MASTER);
    int base_menu = menu_of_enum(active_base);
    if (cur_menu >= 0 && base_menu >= 0) {
        itoa_dec(base_menu, buf); call1(H_SETMODE, buf);
        call1(H_EFF, "0"); call1(H_CON, "0"); call1(H_SHP, "0");
        call1(H_SAT, "0"); call1(H_TON, "0");
        itoa_dec(cur_menu, buf);  call1(H_SETMODE, buf);
    }
    backup_valid = 0;
    active = 0;
    active_base = 0;
    cur_idx = 0;
    last_variant = 0;
}

void monitor_main(void)
{
    u32 boot_ok = 0;
    u8 prev = 0;

    for (u32 i = 0; i < BOOT_CHECKS; i++) {
        u8 m = MODE_MASTER;
        if (m == prev && m <= 0x24) boot_ok++;
        prev = m;
        DLY_TSK(POLL_MS);
    }
    if (boot_ok < BOOT_CHECKS - 2) {
        for (;;) DLY_TSK(1000);
    }

    for (;;) {
        u8 m = MODE_MASTER;

        if (m >= VAR_FIRST && m <= VAR_LAST) {
            if (last_variant != m) {
                if (m - VAR_FIRST != cur_idx || !active) {
                    cur_idx = m - VAR_FIRST;
                    flash_on_next = 1;
                }
                last_variant = m;
                settling = 1;
                settle_ctr = SETTLE_LOOPS;
            } else if (settling) {
                if (--settle_ctr == 0) {
                    settling = 0;
                    const look_t *lk = &g_looks[cur_idx];
                    if (lk->valid) apply_look(lk);
                }
            }
        } else {
            settling = 0;
            if (active && m != active_base) {
                exit_look();
            }
            if (!active) last_variant = 0;
        }
        if (active) flash_pump();
        if (boot_ticks < 0xFFFF) boot_ticks++;
        DLY_TSK(POLL_MS);
    }
}
