# bepinex-plugin

A BepInEx 5 plugin for Unity games that ship Mono assemblies (`*_Data/Managed/
Assembly-CSharp.dll`). It logs when it loads and patches `UnityEngine.Debug.Log`
with Harmony as a demo.

BepInEx 5 is for Mono games. IL2CPP games (a `GameAssembly.dll` next to the exe,
no `Managed` folder) need BepInEx 6 and dumped metadata from `il2cppdumper`;
this template does not cover that.

## Build

```
dotnet build -c Release -p:GameDir="/path/to/the/game"
```

Without `GameDir` the project still restores (`./test.sh`), so the toolchain can
be checked without a game. With it, `Assembly-CSharp.dll` is referenced from the
game's `Managed` folder and you can patch the game's own classes.

## Install

```
./install.sh "/path/to/the/game"
```

Copies BepInEx from `~/re/tools/bepinex` into the game if it is not there yet,
then puts the plugin into `BepInEx/plugins/`.

Steam launch options: `WINEDLLOVERRIDES="winhttp=n,b" %command%`. Under Proton,
BepInEx only starts when Wine prefers the game's `winhttp.dll` over its own.
The log is `BepInEx/LogOutput.log` in the game folder.

## Patching game code

Open `Assembly-CSharp.dll` with `ilspycmd` or the ILSpy GUI, find the class and
method, then replace the demo patch:

```csharp
[HarmonyPatch(typeof(PlayerHealth), nameof(PlayerHealth.TakeDamage))]
[HarmonyPrefix]
static bool NoDamage() => false;   // skip the original
```

A prefix that returns `false` skips the original method. A postfix runs after it
and can read or change the result with `ref __result`.
