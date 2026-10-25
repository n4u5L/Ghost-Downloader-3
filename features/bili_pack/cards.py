from __future__ import annotations

from urllib.parse import urlencode, urlparse
import re

from loguru import logger

from app.client import buildClient
from app.i18n import tr
from app.ui.components.media import Storyboard
from app.ui.dialogs.media_select import MediaSelectDialog
from .task import setEpisodeTitle


def buildSelection(task, host, *, shouldUpdate=True):
    groups = [(pages[0].episodeTitle or pages[0].bvid, pages) for pages in task.episodeGroups()]
    def rename(index, name):
        page = next(file for file in task.files if file.index == index)
        episode = [file for file in task.files if file.bvid == page.bvid]
        if page.episodeTitle and len(episode) == 1:
            setEpisodeTitle(episode, name)
        else:
            page.pagePart = name
    dialog = MediaSelectDialog(task, host, rename=rename, update=task.update if shouldUpdate else task.updateNames,
                               groups=groups if task.isSeason else None, renameGroup=setEpisodeTitle)
    dialog.dialog.set_title(tr("SelectDialog", "选择合集" if task.isSeason else "选择分P"))
    return dialog


async def fetchStoryboard(task):
    page = task.files[0] if task.files else None
    if not page or not page.cid:
        return None
    params = {"cid": page.cid, "index": 1}
    video = page.bvid or next(iter(re.findall(r"BV[a-zA-Z0-9]+|av\d+", urlparse(task.url).path)), "")
    if not video:
        return None
    params["aid" if video.startswith("av") else "bvid"] = video[2:] if video.startswith("av") else video
    client = buildClient(headers=page.headers)
    try:
        response = await client.get("https://api.bilibili.com/x/player/videoshot?" + urlencode(params))
        try:
            response.raise_for_status()
            payload = await response.json()
            if payload.get("code", 0) != 0:
                raise ValueError(f"Bilibili storyboard: {payload.get('code')} {payload.get('message', '')}")
            data = payload.get("data") or {}
        finally:
            response.close()
        if not data.get("image") or not data.get("index"):
            logger.warning("Bilibili returned no storyboard for {} (cid={})", video, page.cid)
            return None
        return Storyboard(["https:" + url if url.startswith("//") else url for url in data.get("image") or []],
                          data.get("index") or [], max(1, int(data.get("img_x_len") or 10)),
                          max(1, int(data.get("img_y_len") or 10)), dict(page.headers))
    finally:
        client.close()
