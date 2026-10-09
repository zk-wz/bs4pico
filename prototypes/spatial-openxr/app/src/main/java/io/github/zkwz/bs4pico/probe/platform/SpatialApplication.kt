package io.github.zkwz.bs4pico.probe.platform

import android.app.Activity
import android.app.Application
import android.util.Log
import com.pico.spatial.ui.foundation.dsl.launch
import io.github.zkwz.bs4pico.probe.mainApp
import java.lang.ref.WeakReference

class SpatialApplication : Application() {
    private var sceneActivity: WeakReference<Activity>? = null
    private var retiringNative: WeakReference<VrActivity>? = null
    private var pendingManager: WeakReference<LaunchActivity>? = null

    // PICO may put planar and immersive Activities in different Android tasks.
    // Foreground ownership therefore cannot rely on the task back stack alone.
    fun activateScene(activity: Activity) {
        val previous = sceneActivity?.get()
        sceneActivity = WeakReference(activity)
        if (previous === activity) return
        when (previous) {
            is VrActivity -> if (!previous.isDestroyed) {
                retiringNative = WeakReference(previous)
                previous.finishForReplacement()
            }
            is LaunchActivity -> previous.finish()
        }
    }

    fun requestNative(manager: LaunchActivity) {
        if (retiringNative?.get()?.isDestroyed == false) {
            pendingManager = WeakReference(manager)
            Log.i("BS4PicoProbe", "native entry waiting for previous Activity.onDestroy")
        } else {
            manager.launchNativeNow()
        }
    }

    fun onNativeDestroyed(activity: VrActivity) {
        if (retiringNative?.get() !== activity) return
        retiringNative = null
        val manager = pendingManager?.get()
        pendingManager = null
        // Run after Android's destroy transaction has returned, not while the
        // old immersive Activity is still being acknowledged to system_server.
        manager?.window?.decorView?.post {
            if (!manager.isDestroyed && !manager.isFinishing) manager.launchNativeNow()
        }
    }

    override fun onCreate() {
        super.onCreate()
        launch(::mainApp)
    }
}
