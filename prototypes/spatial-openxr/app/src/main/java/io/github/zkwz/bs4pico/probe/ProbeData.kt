package io.github.zkwz.bs4pico.probe

import android.content.Context
import android.os.Process
import android.util.AtomicFile
import android.util.Log
import java.io.File

/** Durable handoff; only the foreground side writes, before handing over its Activity. */
object ProbeData {
    fun file(context: Context) = File(context.filesDir, "switch-probe.txt")

    fun read(context: Context): String {
        val target = file(context)
        if (!target.exists()) write(context, 0, 0)
        val data = target.readText()
        Log.i("BS4PicoProbe", "pid=${Process.myPid()} private read data=${data.replace('\n', ' ')}")
        return data
    }

    fun prepareVisit(context: Context): String {
        val values = read(context).lineSequence().mapNotNull {
            val pair = it.split('=', limit = 2)
            if (pair.size == 2) pair[0] to pair[1] else null
        }.toMap()
        write(context, values.getValue("manager_generation").toLong() + 1,
            values.getValue("native_visits").toLong())
        return read(context)
    }

    private fun write(context: Context, generation: Long, visits: Long) {
        val data = "manager_generation=$generation\nnative_visits=$visits\nlast_writer=manager\n"
        val target = AtomicFile(file(context))
        val stream = target.startWrite()
        try {
            stream.write(data.toByteArray(Charsets.UTF_8))
            target.finishWrite(stream)
            Log.i("BS4PicoProbe", "private write path=${file(context)} data=${data.replace('\n', ' ')}")
        } catch (failure: Exception) {
            target.failWrite(stream)
            throw failure
        }
    }
}
