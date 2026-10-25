# 功能包界面

功能包的 `pack.py`、`task.py`、`config.py` 负责业务，不导入 Qt 或 bkit。
桌面宿主通过 `app.ui.pack.PackViews` 在第一次需要某个功能包的界面时加载同目录的 `ui.py`。
`ui.py` 导出继承 `app.ui.pack.PackUi` 的 `PackUi` 类。没有界面入口的包使用通用界面。

每个界面实例显式接收业务包和 `PackUiServices`，可组合以下界面：

| 方法 | 返回值 |
|---|---|
| `taskCard(task, copyUrls, openDrawer)` | 任务列表节点，支持 `refresh()` |
| `draftCard(task, probeConflict)` | 解析结果节点，支持 `applyOptions()`、`overrides()` |
| `options(task, isEditing=False)` | 逐任务选项，每项提供 `apply() -> bool` |
| `details(task)` | 详情节点，每项提供 `refresh() -> bool` |
| `settings()` | 设置卡片组 |

界面使用 bkit 的 `Node`、`Row`、`Column`、`LazyColumn`、输入框和 Material 控件组合。
自定义控件继承 `ui.Node`，把 `ui.Box`、`ui.Image` 等原生控件作为子节点组合；
原生控件不允许继承。
业务操作调用已有 Service；界面订阅信号投影状态。异步任务通过
`services.coroutineRunner.submit()` 执行，完成回调由宿主投递到 UI 线程。
原生文件对话框通过 `services.uiLoop.post()` 打开。

附加页面在 `manifest.toml` 中声明导航信息，点击导航项后才导入模块和创建页面：

```toml
[[ui.pages]]
title = "资源下载"
icon = "cloud"
module = "pages"
class = "CatalogPage"
```

页面构造函数接收 `(pack, services, host)`。导航信息不需要导入功能包的 UI 模块。
设置组通过 `setCardsBuilder(build)` 和 `addSettingCardFactory(build)` 延迟创建内容，
展开或搜索时才实例化设置控件。长列表使用 `LazyColumn`，编辑状态保存在数据中。

通用任务选项提供目录和线程数。草稿通过 `TaskDraft.setUrlOptions()` 保存逐任务覆盖值，
确认任务时与全局默认值合并。功能包专用选项由各包的 `options()` 构建。
通用选项草稿位于 `app/ui/cards/options.py`。Bilibili 的视频、音频、字幕、封面按钮
直接放在结果行；点击裁剪按钮展开时间范围，关闭裁剪时重置范围。
控件直接修改草稿，不增加媒体设置对话框或预览确认步骤。
运行中任务的修改通过 Task Service 提交；更换下载链接时先解析并确认内容是否可续传。

列表和详情支持原生懒加载。周期回调在节点脱离窗口时取消；请求成功后更新节点属性，
不在绘制或布局回调中增删子节点。旧 Qt 入口的通用界面位于 `app/view/features.py`，
不再从功能包请求 Qt 控件。

裁剪滑条位于 `app/ui/components/range_slider.py`，沿用 Qt 控件的 50dp 几何布局和输入规则：
时间气泡跟随手柄，点击气泡时才创建就地输入框，回车或失焦提交；点击轨道立即移动最近手柄，
左右手柄互相约束且允许重合，接近时错开两个时间标签。展开裁剪本身不修改任务，
拖动或提交时间编辑时才更新范围；关闭裁剪重置任务范围。

展开裁剪时读取预览索引，悬停或拖动滑条时在指针上方弹出当前帧，移出时隐藏。
只请求当前帧所在的精灵图，后台通过 Windows WIC 先裁剪单格并缩放到 160×90 的显示尺寸
（按 DPI 调整），再把小图交给 bkit；UI 不持有整张精灵图位图，也不通过放大整图、图层裁切显示单帧。
预览缓存由所有功能包共用，压缩数据上限 2 MiB，缩略图像素上限 1 MiB、最多 16 帧；
单个编辑器串行处理图片并合并拖动请求。关闭裁剪、移除草稿时取消请求并移除对应缓存，
过期回调不再解码。选集窗口仅为修改过的文件保存编辑数据，关闭时清空懒列表及文件引用。

系统通知后端在首次发送通知时初始化；BT 会话在解析磁力、开始下载或查询 DHT 状态时创建，
避免尚未使用这些功能时就分配其后台资源。
