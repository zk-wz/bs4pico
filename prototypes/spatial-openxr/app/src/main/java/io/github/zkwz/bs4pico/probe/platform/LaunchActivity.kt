package io.github.zkwz.bs4pico.probe.platform

import android.content.Intent
import android.os.Bundle
import android.os.Process
import android.util.Log
import android.view.ViewTreeObserver
import androidx.compose.runtime.mutableStateOf
import com.pico.spatial.ui.platform.stub.SpatialLaunchActivity
import io.github.zkwz.bs4pico.probe.BuildConfig
import io.github.zkwz.bs4pico.probe.ProbeData

class LaunchActivity : SpatialLaunchActivity() {
    val data = mutableStateOf("")
    private var entering = false
    private var draws = 0L
    private val drawObserver = ViewTreeObserver.OnDrawListener { draws++ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        (application as SpatialApplication).activateScene(this)
        window.decorView.viewTreeObserver.addOnDrawListener(drawObserver)
        log("onCreate restored=${savedInstanceState != null}")
    }

    override fun onStart() { super.onStart(); log("onStart") }
    override fun onResume() {
        super.onResume()
        data.value = ProbeData.read(this)
        log("onResume data=${data.value.replace('\n', ' ')}")
        runDebugAction()
    }
    override fun onPause() { log("onPause"); super.onPause() }
    override fun onStop() { log("onStop"); super.onStop() }
    override fun onDestroy() {
        window.decorView.viewTreeObserver.removeOnDrawListener(drawObserver)
        log("onDestroy manager surface disposed")
        super.onDestroy()
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        runDebugAction()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        log("onSaveInstanceState")
        super.onSaveInstanceState(outState)
    }

    fun enterVr() {
        if (entering) return
        entering = true
        data.value = ProbeData.prepareVisit(this)
        log("switch manager -> native")
        (application as SpatialApplication).requestNative(this)
    }

    fun launchNativeNow() {
        startActivity(Intent(this, VrActivity::class.java).also {
            if (BuildConfig.DEBUG) it.putExtra("probe_haptics", intent.getBooleanExtra("probe_haptics", false))
        })
        // Deliberately destroy, rather than keep an invisible Spatial renderer alive.
        finish()
    }

    private fun runDebugAction() {
        if (!BuildConfig.DEBUG) return
        val action = intent.getStringExtra("probe_action") ?: return
        intent.removeExtra("probe_action")
        window.decorView.post {
            when (action) {
                "enter" -> enterVr()
                "recreate" -> recreate()
                "finish" -> finish()
            }
        }
    }

    private fun log(event: String) {
        Log.i("BS4PicoProbe", "pid=${Process.myPid()} activity=${System.identityHashCode(this)} Manager@${System.identityHashCode(this)} $event draws=$draws task=$taskId")
    }
}
