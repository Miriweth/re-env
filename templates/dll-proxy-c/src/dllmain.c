/* Mod entry point. Replace the Sleep hook in mod_main with your own hooks;
 * target addresses come from Ghidra (module base + RVA) or a pattern scan. */
#include <windows.h>
#include <stdio.h>
#include <MinHook.h>
#include "proxy.h"

static void log_line(const char *msg)
{
    FILE *f = fopen("mod.log", "a");
    if (!f)
        return;
    fprintf(f, "%s\n", msg);
    fclose(f);
}

typedef VOID (WINAPI *Sleep_t)(DWORD);
static Sleep_t real_Sleep;

static VOID WINAPI hook_Sleep(DWORD ms)
{
    char buf[64];
    snprintf(buf, sizeof buf, "Sleep(%lu)", (unsigned long)ms);
    log_line(buf);
    real_Sleep(ms);
}

static DWORD WINAPI mod_main(LPVOID arg)
{
    (void)arg;
    if (MH_Initialize() != MH_OK) {
        log_line("MH_Initialize failed");
        return 1;
    }
    if (MH_CreateHookApi(L"kernel32", "Sleep", (LPVOID)hook_Sleep, (LPVOID *)&real_Sleep) != MH_OK) {
        log_line("hook Sleep failed");
        return 1;
    }
    MH_EnableHook(MH_ALL_HOOKS);
    log_line("mod loaded, hooks enabled");
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        proxy_init();
        CloseHandle(CreateThread(NULL, 0, mod_main, NULL, 0, NULL));
    }
    return TRUE;
}
