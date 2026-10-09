package io.github.zkwz.bs4pico.probe.content

import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.pico.spatial.ui.design.Button
import com.pico.spatial.ui.design.PicoTheme
import com.pico.spatial.ui.design.Text
import io.github.zkwz.bs4pico.probe.platform.LaunchActivity

private tailrec fun Context.manager(): LaunchActivity =
    when (this) {
        is LaunchActivity -> this
        is ContextWrapper -> baseContext.manager()
        else -> error("Manager content requires LaunchActivity")
    }

@Composable
fun HomePage() {
    val activity = LocalContext.current.manager()
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Text("BS for Pico · Spatial / OpenXR 切换验证",
            color = PicoTheme.colorScheme.labelPrimary)
        Text("此界面使用 PICO Spatial SDK。进入 VR 时销毁管理 Activity，返回后重新读取私有文件。",
            color = PicoTheme.colorScheme.labelPrimary)
        Text(activity.data.value, color = PicoTheme.colorScheme.labelPrimary)
        Button(onClick = activity::enterVr) { Text("进入 VR") }
        Text("VR 中按返回键或手柄退出动作返回管理界面。OpenXR 失败不会伪装成平面 VR。",
            color = PicoTheme.colorScheme.labelPrimary)
    }
}
