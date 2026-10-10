package io.github.zkwz.bs4pico.probe.platform

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Process
import android.util.Log
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import androidx.annotation.Keep
import io.github.zkwz.bs4pico.probe.BuildConfig
import io.github.zkwz.bs4pico.probe.ProbeData

/** Surface/foreground jointly own one worker; no Spatial container is created here. */
class VrActivity : Activity(), SurfaceHolder.Callback {
    private var surface: Surface? = null
    private var resumed = false
    private var handle = 0L
    private var returning = false
    @Volatile private var nativeEpoch = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        (application as SpatialApplication).activateScene(this)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(SurfaceView(this).also { it.holder.addCallback(this) })
        log("onCreate restored=${savedInstanceState != null} direct=${intent.getBooleanExtra("direct", false)}")
        ProbeData.read(this)
    }
    override fun onStart() { super.onStart(); log("onStart") }
    override fun onResume() {
        super.onResume()
        resumed = true
        log("onResume")
        startIfReady()
        runDebugAction()
    }
    override fun onPause() {
        resumed = false
        log("onPause")
        stopNative()
        super.onPause()
    }
    override fun onStop() { log("onStop"); super.onStop() }
    override fun onDestroy() {
        stopNative()
        log("onDestroy")
        super.onDestroy()
        (application as SpatialApplication).onNativeDestroyed(this)
    }
    override fun onSaveInstanceState(outState: Bundle) {
        log("onSaveInstanceState")
        super.onSaveInstanceState(outState)
    }
    override fun surfaceCreated(holder: SurfaceHolder) {
        surface = holder.surface
        log("surfaceCreated")
        startIfReady()
    }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        log("surfaceChanged ${width}x$height format=$format")
    }
    override fun surfaceDestroyed(holder: SurfaceHolder) {
        log("surfaceDestroyed")
        surface = null
        stopNative()
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        runDebugAction()
    }
    @Suppress("DEPRECATION")
    override fun onBackPressed() = returnToManager()

    private fun startIfReady() {
        val currentSurface = surface ?: return
        if (!resumed || handle != 0L || returning || !currentSurface.isValid) return
        nativeEpoch++
        handle = nativeStart(currentSurface, ProbeData.file(this).absolutePath,
            System.identityHashCode(this), nativeEpoch,
            BuildConfig.DEBUG && intent.getBooleanExtra("probe_haptics", false))
        log("nativeStart handle=$handle epoch=$nativeEpoch")
    }
    private fun stopNative() {
        if (handle == 0L) return
        val current = handle
        handle = 0L
        nativeEpoch++
        nativeStop(current)
        log("nativeStop joined handle=$current")
    }
    fun finishForReplacement() {
        returning = true
        stopNative()
        log("scene ownership replaced; native retired")
        finish()
    }

    private fun returnToManager() {
        if (returning) return
        returning = true
        stopNative()
        log("switch native -> manager")
        startActivity(Intent(this, LaunchActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    // Worker callbacks never mutate Activity state off the main thread.
    @Keep fun onNativeStatus(message: String) { Log.i("BS4PicoProbe", "XR status $message") }
    @Keep fun onNativeExit() {
        val epoch = nativeEpoch
        runOnUiThread { if (resumed && !returning && epoch == nativeEpoch) returnToManager() }
    }
    private fun runDebugAction() {
        if (!BuildConfig.DEBUG) return
        val action = intent.getStringExtra("probe_action") ?: return
        intent.removeExtra("probe_action")
        window.decorView.post {
            when (action) {
                "return" -> returnToManager()
                "recreate" -> recreate()
            }
        }
    }
    private fun log(event: String) {
        Log.i("BS4PicoProbe", "pid=${Process.myPid()} activity=${System.identityHashCode(this)} epoch=$nativeEpoch Native@${System.identityHashCode(this)} $event task=$taskId")
    }
    private external fun nativeStart(surface: Surface, dataPath: String, activityId: Int, epoch: Long, hapticProbe: Boolean): Long
    private external fun nativeStop(handle: Long)
    companion object { init { System.loadLibrary("xrprobe") } }
}
