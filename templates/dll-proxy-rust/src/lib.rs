//! Proxy dinput8.dll: forwards DirectInput8Create to the real System32 DLL and
//! runs mod_main on its own thread. Put your hooks into mod_main.

use std::ffi::c_void;
use std::io::Write;
use std::sync::OnceLock;

use windows_sys::core::{GUID, HRESULT};
use windows_sys::Win32::Foundation::{CloseHandle, E_FAIL, HINSTANCE, HMODULE, TRUE};
use windows_sys::Win32::System::LibraryLoader::{DisableThreadLibraryCalls, GetProcAddress, LoadLibraryW};
use windows_sys::Win32::System::SystemInformation::GetSystemDirectoryW;
use windows_sys::Win32::System::SystemServices::DLL_PROCESS_ATTACH;
use windows_sys::Win32::System::Threading::CreateThread;

type DirectInput8CreateFn =
    unsafe extern "system" fn(HINSTANCE, u32, *const GUID, *mut *mut c_void, *mut c_void) -> HRESULT;

static REAL: OnceLock<Option<DirectInput8CreateFn>> = OnceLock::new();

fn load_real() -> Option<DirectInput8CreateFn> {
    unsafe {
        let mut dir = [0u16; 260];
        let n = GetSystemDirectoryW(dir.as_mut_ptr(), dir.len() as u32) as usize;
        if n == 0 || n >= dir.len() {
            return None;
        }
        let mut path: Vec<u16> = dir[..n].to_vec();
        path.extend("\\dinput8.dll\0".encode_utf16());
        let real: HMODULE = LoadLibraryW(path.as_ptr());
        if real.is_null() {
            return None;
        }
        let f = GetProcAddress(real, c"DirectInput8Create".as_ptr().cast())?;
        Some(std::mem::transmute::<unsafe extern "system" fn() -> isize, DirectInput8CreateFn>(f))
    }
}

#[no_mangle]
pub unsafe extern "system" fn DirectInput8Create(
    hinst: HINSTANCE,
    version: u32,
    riid: *const GUID,
    out: *mut *mut c_void,
    punk: *mut c_void,
) -> HRESULT {
    match REAL.get_or_init(load_real) {
        Some(real) => real(hinst, version, riid, out, punk),
        None => E_FAIL,
    }
}

fn log_line(msg: &str) {
    if let Ok(mut f) = std::fs::OpenOptions::new().append(true).create(true).open("mod.log") {
        let _ = writeln!(f, "{msg}");
    }
}

/// Runs on its own thread after the DLL is loaded. Hooks go here.
unsafe extern "system" fn mod_main(_: *mut c_void) -> u32 {
    log_line("mod loaded (dinput8 proxy)");
    0
}

#[no_mangle]
pub unsafe extern "system" fn DllMain(inst: HINSTANCE, reason: u32, _reserved: *mut c_void) -> i32 {
    if reason == DLL_PROCESS_ATTACH {
        DisableThreadLibraryCalls(inst);
        let h = CreateThread(std::ptr::null(), 0, Some(mod_main), std::ptr::null(), 0, std::ptr::null_mut());
        if !h.is_null() {
            CloseHandle(h);
        }
    }
    TRUE
}
