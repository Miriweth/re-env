/* version.dll proxy: every export jumps straight into the real System32 DLL.
 *
 * Each PROXY(name) defines a pointer p_<name> and an exported asm stub that
 * does `jmp *p_<name>`; the stack and registers are untouched, so we never
 * need the real signatures. version.def lists the same names as exports.
 */
#include <windows.h>
#include "proxy.h"

/* `.text` matters: at -O0 the assembler would otherwise still be in .bss
 * after the variable, and a jmp in .bss is zero-filled and not executable. */
#define PROXY(name) \
    void *p_##name; \
    __asm__(".text\n.globl " #name "\n" #name ":\n\tjmp *p_" #name "(%rip)\n");
#define RESOLVE(name) p_##name = (void *)GetProcAddress(real, #name);

#define FOR_EACH_EXPORT(X) \
    X(GetFileVersionInfoA) X(GetFileVersionInfoW) \
    X(GetFileVersionInfoExA) X(GetFileVersionInfoExW) \
    X(GetFileVersionInfoSizeA) X(GetFileVersionInfoSizeW) \
    X(GetFileVersionInfoSizeExA) X(GetFileVersionInfoSizeExW) \
    X(VerFindFileA) X(VerFindFileW) \
    X(VerInstallFileA) X(VerInstallFileW) \
    X(VerLanguageNameA) X(VerLanguageNameW) \
    X(VerQueryValueA) X(VerQueryValueW)

FOR_EACH_EXPORT(PROXY)

void proxy_init(void)
{
    char path[MAX_PATH];
    UINT n = GetSystemDirectoryA(path, MAX_PATH);
    if (n == 0 || n + sizeof("\\version.dll") > MAX_PATH)
        return;
    lstrcatA(path, "\\version.dll");
    HMODULE real = LoadLibraryA(path);
    if (!real)
        return;
    FOR_EACH_EXPORT(RESOLVE)
}
