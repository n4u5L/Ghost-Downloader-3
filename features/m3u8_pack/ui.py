from app.ui.pack import PackUi as BasePackUi
from app.i18n import tr
from .config import m3u8Config


LABELS = {'installFolder': ('N_m3u8DL-RE 安装目录', ''),
 'outputFormat': ('输出容器', '点播下载完成后优先使用 ffmpeg 混流为指定容器'),
 'threadCount': ('分片线程数', '传给 N_m3u8DL-RE 的下载线程数'),
 'retryCount': ('分片重试次数', '单个分片下载失败时的最大重试次数'),
 'requestTimeout': ('请求超时', 'HTTP 请求超时时间'),
 'shouldAutoSelect': ('自动选择最佳轨道', '默认选择最佳音视频轨道'),
 'shouldConcurrentDownload': ('并发下载音视频', '同时下载已选择的音频、视频和字幕轨道'),
 'shouldAppendUrlParams': ('追加 URL 参数', '把输入链接上的 Query 参数追加到分片请求'),
 'shouldBinaryMerge': ('二进制合并', '让 N_m3u8DL-RE 使用二进制方式合并分片'),
 'shouldCheckSegmentsCount': ('校验分片数量', '下载完成后检查实际分片数是否与预期一致'),
 'shouldKeepLiveSegments': ('直播保留原始分片', '实时合并录制时仍保留下载的原始分片'),
 'shouldUseLivePipeMux': ('直播管道混流', '录制时通过管道交给 ffmpeg 实时混流为封装容器'),
 'shouldFixLiveVtt': ('直播校正 VTT 字幕', '根据音频起始时间校正 VTT 字幕时间轴'),
 'liveWaitTime': ('直播刷新等待时间', '两次拉取直播清单之间的等待秒数，0 为自动'),
 'liveTakeCount': ('直播每次取片数', '每次刷新最多取走的分片数量，0 为自动'),
 'decryptionEngine': ('解密引擎', '调用的第三方解密程序'),
 'decryptionBinaryPath': ('解密引擎二进制路径', 'MP4Decrypt / Shaka Packager 可执行文件路径，留空则使用 FFmpeg'),
 'shouldUseMp4RealTimeDecryption': ('MP4 实时解密', '下载 MP4 分片时实时解密'),
 'maxSpeed': ('限速', '最大下载速度，-1 为不限速'),
 'speedUnit': ('限速单位', '限速数值的单位'),
 'adKeyword': ('广告过滤', '匹配广告分片 URL 的正则表达式'),
 'subtitleFormat': ('字幕格式', '字幕输出格式'),
 'shouldOmitDateInfo': ('不写入日期信息', '混流时不写入日期信息'),
 'shouldKeepImageSegments': ('保留图形分片', '把图形字幕转图片后保留原始分片'),
 'shouldDeleteTemp': ('完成后删除临时文件', '下载完成后删除分片临时目录'),
 'shouldSelectAllAudioSubtitle': ('下载全部音轨与字幕', '默认拉取全部音频与字幕轨道'),
 'customMuxAfterDone': ('自定义混流参数', '自定义 --mux-after-done，留空则按输出容器自动混流')}


class PackUi(BasePackUi):
    editKeys = ("headers", "recordLimit", "selectVideo", "decryptionKeys", "decryptionKeyFile", "muxImports")
    def settings(self):
        from app.ui.components.pack_controls import buildConfigGroup
        labels = {name: (tr('M3U8Config', label), tr('M3U8Config', description)) for name, (label, description) in LABELS.items()}
        return [buildConfigGroup(m3u8Config, tr('M3U8Config', 'M3U8 下载'), 'm3u8_pack',
                                 labels, self.services.uiLoop.post)]

    def taskCard(self, task, copyUrls, openDrawer):
        from .cards import M3U8TaskCard
        return M3U8TaskCard(task, self.services.taskService, self.services.categoryService, copyUrls, openDrawer)

    def options(self, task, isEditing=False):
        import json
        from app.ui.components.pack_controls import TextOption, ChoiceOption, FileOption, parseHeaders
        step = task.steps[0] if task.steps else None
        if step is None:
            return []
        def save(key):
            return lambda value: task.setOptions({key: value})
        cards = [TextOption(tr("HeadersEditCard", "请求头"), json.dumps(step.headers, ensure_ascii=False),
                            save("headers"), parse=parseHeaders, multiline=True)]
        if not isEditing and len(task.streams) > 1:
            choices = [("", tr("StreamSelectCard", "默认（最佳）"))]
            for stream in task.streams:
                width, height = stream.get("width", 0), stream.get("height", 0)
                rate = stream.get("frameRate")
                value = f'res="{width}x{height}"' + (f':frame="{int(rate)}*"' if rate else "")
                choices.append((value, f"{width}×{height} {stream.get('codecs', '')} {rate or ''}"))
            cards.append(ChoiceOption(tr("StreamSelectCard", "视频轨道"), choices, step.selectVideo, save("selectVideo")))
        if task.isLive:
            def parseLimit(value):
                from app.ui.components.media import parseTime
                seconds = parseTime(value)
                return f"{seconds // 3600:02}:{seconds % 3600 // 60:02}:{seconds % 60:02}" if seconds else ""
            cards.append(TextOption(tr("RecordLimitCard", "录制时长"), step.recordLimit, save("recordLimit"), parse=parseLimit))
        cards.extend([
            TextOption(tr("DecryptionKeyCard", "解密密钥"), "\n".join(step.decryptionKeys), save("decryptionKeys"),
                       parse=lambda value: [line.strip() for line in value.splitlines() if line.strip()], multiline=True),
            FileOption(tr("DecryptionKeyCard", "KEY 文本文件"), step.decryptionKeyFile, save("decryptionKeyFile"), self.services.uiLoop.post),
            TextOption(tr("MuxImportCard", "导入音轨/字幕"), "\n".join(step.muxImports), save("muxImports"),
                       parse=lambda value: [line.strip() for line in value.splitlines() if line.strip()], multiline=True),
        ])
        return cards
