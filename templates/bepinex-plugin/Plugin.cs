using BepInEx;
using HarmonyLib;

namespace ExamplePlugin;

[BepInPlugin("re.example.plugin", "ExamplePlugin", "0.1.0")]
public class Plugin : BaseUnityPlugin
{
    private void Awake()
    {
        Logger.LogInfo("ExamplePlugin loaded");
        Harmony.CreateAndPatchAll(typeof(Plugin));
    }

    // Demo patch: mirror every Debug.Log(object) call into the plugin log.
    // Replace the target with a game class from Assembly-CSharp (see README).
    [HarmonyPatch(typeof(UnityEngine.Debug), nameof(UnityEngine.Debug.Log), typeof(object))]
    [HarmonyPrefix]
    private static void DebugLogPrefix(object message)
    {
        BepInEx.Logging.Logger.CreateLogSource("ExamplePlugin").LogDebug($"Debug.Log: {message}");
    }
}
