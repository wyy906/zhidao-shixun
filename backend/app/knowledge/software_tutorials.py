"""软件使用教程知识库

按识别到的软件匹配对应教程，供「通用屏幕指导」使用。
每个教程包含：显示名、别名（用于匹配）、简介、若干步骤（步骤含 keywords 用于定位界面控件）。
"""
from __future__ import annotations


TUTORIALS: dict[str, dict] = {
    "doubao": {
        "display_name": "豆包",
        "aliases": ["doubao", "豆包", "doubao.exe", "doubao app"],
        "intro": "字节跳动的 AI 助手，支持对话问答、写作、翻译、图片生成等。",
        "steps": [
            {
                "title": "开始新对话",
                "detail": "点击左上角的「新建对话」（或「+」号），开启一个全新的对话。",
                "keywords": ["新建对话", "新对话", "新会话", "new chat", "新建"],
                "type_hint": "button",
            },
            {
                "title": "输入问题并发送",
                "detail": "在底部输入框里输入你的问题，按回车或点击发送按钮。",
                "keywords": ["输入", "发送", "问", "ask", "send", "输入框", "写点什么"],
                "type_hint": "edit",
            },
            {
                "title": "上传文件或图片",
                "detail": "点击输入框旁的回形针/图片按钮，选择本地文件上传给豆包分析。",
                "keywords": ["上传", "附件", "图片", "文件", "回形针", "attach"],
                "type_hint": "button",
            },
            {
                "title": "查看历史对话",
                "detail": "左侧列表可切换历史会话；点击右上角头像可进入设置。",
                "keywords": ["历史", "会话", "对话列表", "设置", "头像", "history"],
                "type_hint": "button",
            },
        ],
    },
    "trae": {
        "display_name": "Trae / SOLO",
        "aliases": ["trae", "solo", "trae.exe", "trae ai", "marvis"],
        "intro": "Trae 是 AI 编程 IDE，SOLO 模式让 AI 自主完成任务。",
        "steps": [
            {
                "title": "开启新对话",
                "detail": "点击左上角「新建对话」，开始一个新的编程任务。",
                "keywords": ["新建对话", "新建会话", "new chat", "新会话"],
                "type_hint": "button",
            },
            {
                "title": "描述你的需求",
                "detail": "在输入框里描述你想实现的功能，按回车发送。",
                "keywords": ["输入", "写", "描述", "输入框", "ask", "给 ai"],
                "type_hint": "edit",
            },
            {
                "title": "添加文件/上下文",
                "detail": "点击「添加上下文」把相关文件加入对话，帮助 AI 理解项目。",
                "keywords": ["添加上下文", "上下文", "context", "添加文件"],
                "type_hint": "button",
            },
            {
                "title": "查看生成结果",
                "detail": "在对话区查看 AI 输出，右侧可查看文件改动并确认应用。",
                "keywords": ["应用", "确认", "accept", "文件", "diff", "更改"],
                "type_hint": "button",
            },
        ],
    },
    "chrome": {
        "display_name": "浏览器（Chrome / Edge）",
        "aliases": ["chrome", "chrome.exe", "edge", "msedge.exe", "google chrome", "microsoft edge"],
        "intro": "常用网页浏览器，可访问网页、搜索资料、管理标签页。",
        "steps": [
            {
                "title": "输入网址或搜索",
                "detail": "点击顶部地址栏，输入网址或关键词后按回车。",
                "keywords": ["地址栏", "搜索", "网址", "search", "address", "输入"],
                "type_hint": "edit",
            },
            {
                "title": "新建标签页",
                "detail": "按 Ctrl+T 或点击标签栏右侧「+」打开新标签页。",
                "keywords": ["新标签页", "new tab", "加号", "新建标签", "+"],
                "type_hint": "button",
            },
            {
                "title": "刷新页面",
                "detail": "按 F5 或点击地址栏左侧的刷新按钮重新加载。",
                "keywords": ["刷新", "reload", "refresh"],
                "type_hint": "button",
            },
            {
                "title": "收藏书签",
                "detail": "点击地址栏右侧的星标收藏当前网页。",
                "keywords": ["书签", "收藏", "bookmark", "星标"],
                "type_hint": "button",
            },
        ],
    },
    "vscode": {
        "display_name": "VS Code",
        "aliases": ["vs code", "vscode", "code.exe", "visual studio code"],
        "intro": "微软推出的轻量级代码编辑器，支持多种语言和插件。",
        "steps": [
            {
                "title": "打开文件夹",
                "detail": "菜单「文件 → 打开文件夹」，选择一个项目目录。",
                "keywords": ["打开文件夹", "open folder", "文件", "资源管理器"],
                "type_hint": "menuitem",
            },
            {
                "title": "新建文件",
                "detail": "在资源管理器顶部点击「新建文件」图标，命名后开始编辑。",
                "keywords": ["新建文件", "new file", "文件"],
                "type_hint": "button",
            },
            {
                "title": "打开终端",
                "detail": "按 Ctrl+` 或菜单「终端 → 新建终端」。",
                "keywords": ["终端", "terminal", "新建终端"],
                "type_hint": "menuitem",
            },
            {
                "title": "运行代码",
                "detail": "在终端输入运行命令（如 python main.py），或在右上角点运行按钮。",
                "keywords": ["运行", "run", "调试", "debug", "终端"],
                "type_hint": "button",
            },
        ],
    },
    "mysqlworkbench": {
        "display_name": "MySQL Workbench",
        "aliases": ["mysql workbench", "mysqlworkbench", "mysqlworkbench.exe", "workbench"],
        "intro": "MySQL 官方图形化管理工具，可建库建表、执行 SQL。",
        "steps": [
            {
                "title": "创建数据库",
                "detail": "在左侧 Schemas 面板点击绿色「Create Schema」按钮新建数据库。",
                "keywords": ["create schema", "创建", "schema", "新建数据库"],
                "type_hint": "button",
            },
            {
                "title": "编辑 SQL",
                "detail": "点击工具栏的 SQL 图标新建查询，在主编辑区编写 SQL。",
                "keywords": ["sql", "查询", "query", "编辑器", "editor"],
                "type_hint": "button",
            },
            {
                "title": "执行 SQL",
                "detail": "点击工具栏的闪电图标（Execute）运行 SQL，下方查看结果。",
                "keywords": ["execute", "执行", "闪电", "run", "播放"],
                "type_hint": "button",
            },
            {
                "title": "应用改动",
                "detail": "修改表结构后点击「Apply」确认执行变更。",
                "keywords": ["apply", "应用", "确认", "确定"],
                "type_hint": "button",
            },
        ],
    },
    "wechat": {
        "display_name": "微信",
        "aliases": ["wechat", "weixin", "微信", "wechat.exe", "weixin.exe"],
        "intro": "常用即时通讯软件，支持聊天、文件传输、朋友圈。",
        "steps": [
            {
                "title": "搜索联系人",
                "detail": "点击顶部搜索框，输入联系人昵称或备注名。",
                "keywords": ["搜索", "查找", "search", "搜索框"],
                "type_hint": "edit",
            },
            {
                "title": "打开聊天",
                "detail": "在搜索结果中点击联系人，进入聊天窗口。",
                "keywords": ["聊天", "联系人", "会话", "chat"],
                "type_hint": "button",
            },
            {
                "title": "发送消息",
                "detail": "在底部输入框输入内容，按回车或点击发送。",
                "keywords": ["发送", "send", "输入", "消息"],
                "type_hint": "edit",
            },
            {
                "title": "发送文件",
                "detail": "点击输入框上方的文件夹图标，选择文件发送。",
                "keywords": ["文件", "文件夹", "发送文件", "attach"],
                "type_hint": "button",
            },
        ],
    },
    "office": {
        "display_name": "Word / Excel",
        "aliases": ["winword", "word", "excel", "winword.exe", "excel.exe", "microsoft word", "microsoft excel"],
        "intro": "微软办公套件，用于文档编辑与表格数据处理。",
        "steps": [
            {
                "title": "新建文档",
                "detail": "点击「文件 → 新建」或使用开始页的「空白文档」模板。",
                "keywords": ["新建", "空白文档", "new", "空白工作簿"],
                "type_hint": "button",
            },
            {
                "title": "编辑内容",
                "detail": "在正文区域点击即可输入文字（Excel 为单元格输入）。",
                "keywords": ["编辑", "输入", "正文", "单元格", "sheet"],
                "type_hint": "edit",
            },
            {
                "title": "插入表格/图表",
                "detail": "菜单「插入」→ 选择表格或图表类型。",
                "keywords": ["插入", "表格", "图表", "insert", "table"],
                "type_hint": "menuitem",
            },
            {
                "title": "保存文件",
                "detail": "按 Ctrl+S 或点击快速访问工具栏的保存图标。",
                "keywords": ["保存", "save", "另存为"],
                "type_hint": "button",
            },
        ],
    },
    "notepad": {
        "display_name": "记事本",
        "aliases": ["notepad", "notepad.exe", "记事本", "无标题 - notepad"],
        "intro": "Windows 自带文本编辑器，适合练习输入、保存与另存为。",
        "steps": [
            {
                "title": "新建标签页",
                "detail": "点击标签栏右侧的「+」新建一个空白标签页。",
                "keywords": ["添加新标签页", "新建标签页", "new tab"],
                "type_hint": "button",
            },
            {
                "title": "输入文字",
                "detail": "在正文编辑区点击后直接键入内容。",
                "keywords": ["文本编辑器", "编辑区", "document"],
                "type_hint": "document",
            },
            {
                "title": "保存文件",
                "detail": "点击菜单「文件 → 保存」（或按 Ctrl+S），选择保存位置。",
                "keywords": ["文件", "保存", "save"],
                "type_hint": "menuitem",
            },
            {
                "title": "调整格式/缩放",
                "detail": "在「查看」菜单里开关自动换行，或点击右下角调整缩放比例。",
                "keywords": ["查看", "缩放", "自动换行"],
                "type_hint": "menuitem",
            },
        ],
    },
    "windowssettings": {
        "display_name": "Windows 系统设置",
        "aliases": ["systemsettings.exe", "windows 设置", "设置", "settings"],
        "intro": "Windows 系统设置，可配置显示、网络、账户、系统信息与环境变量。",
        "steps": [
            {
                "title": "打开「系统」",
                "detail": "在设置首页点击左侧的「系统」，进入系统相关设置。",
                "keywords": ["系统", "system", "显示"],
                "type_hint": "listitem",
            },
            {
                "title": "进入「关于」",
                "detail": "滚动到底部点击「系统信息 / 关于」，查看设备与系统版本。",
                "keywords": ["关于", "系统信息", "about", "设备信息"],
                "type_hint": "button",
            },
            {
                "title": "打开高级系统设置",
                "detail": "点击「高级系统设置」，打开传统的「系统属性」对话框。",
                "keywords": ["高级系统设置", "系统属性", "高级", "advanced"],
                "type_hint": "button",
            },
            {
                "title": "配置环境变量",
                "detail": "在「系统属性 → 高级」中点击「环境变量」，编辑 Path 等变量。",
                "keywords": ["环境变量", "environment variables"],
                "type_hint": "button",
            },
        ],
    },
    "envvar": {
        "display_name": "环境变量",
        "aliases": ["环境变量", "environment variables", "系统属性"],
        "intro": "配置 JAVA_HOME、Path 等环境变量，是很多开发环境的必备步骤。",
        "steps": [
            {
                "title": "新建用户变量",
                "detail": "在上方「用户变量」区域点击「新建」，输入变量名与变量值。",
                "keywords": ["新建", "new"],
                "type_hint": "button",
            },
            {
                "title": "编辑 Path",
                "detail": "选中 Path 后点击「编辑」，逐条添加上具目录。",
                "keywords": ["path", "编辑", "edit"],
                "type_hint": "button",
            },
            {
                "title": "确认保存",
                "detail": "每一层对话框都点击「确定」保存，环境变量才会真正生效。",
                "keywords": ["确定", "ok", "保存"],
                "type_hint": "button",
            },
        ],
    },
    "explorer": {
        "display_name": "文件资源管理器",
        "aliases": ["文件资源管理器", "file explorer", "主文件夹", "此电脑"],
        "intro": "Windows 文件管理器，用来浏览、新建、复制文件与目录。",
        "steps": [
            {
                "title": "打开地址栏",
                "detail": "点击顶部地址栏，可直接输入文件夹路径并回车跳转。",
                "keywords": ["地址栏", "address", "路径"],
                "type_hint": "edit",
            },
            {
                "title": "新建文件夹",
                "detail": "在空白处右键「新建 → 文件夹」，或点击工具栏的「新建」。",
                "keywords": ["新建", "new"],
                "type_hint": "menuitem",
            },
            {
                "title": "切换视图",
                "detail": "点击「查看」菜单，切换详细信息/大图标等显示方式。",
                "keywords": ["查看", "view"],
                "type_hint": "menuitem",
            },
        ],
    },
    "wps": {
        "display_name": "WPS Office",
        "aliases": ["wps", "wps.exe", "wpp", "et.exe", "wps office", "wps - 工具箱"],
        "intro": "国产办公套件，包含 WPS 文字、表格、演示。",
        "steps": [
            {
                "title": "新建文档",
                "detail": "在首页点击「新建」，选择文字/表格/演示。",
                "keywords": ["新建", "首页", "new"],
                "type_hint": "button",
            },
            {
                "title": "编辑内容",
                "detail": "点击正文区域开始输入内容。",
                "keywords": ["编辑", "正文", "document"],
                "type_hint": "edit",
            },
            {
                "title": "保存文件",
                "detail": "点击「文件 → 另存为」或按 Ctrl+S 保存。",
                "keywords": ["保存", "save", "另存为"],
                "type_hint": "button",
            },
        ],
    },
}


def match_tutorial(*hints: str | None) -> dict | None:
    """根据软件名/窗口标题/进程名等线索匹配教程（别名越长越精确）"""
    text = " ".join(h for h in hints if h).lower()
    if not text:
        return None
    best_t: dict | None = None
    best_score = 0
    for t in TUTORIALS.values():
        score = 0
        for alias in t["aliases"]:
            a = alias.lower()
            if a and a in text:
                score = max(score, len(a))
        if score > best_score:
            best_score = score
            best_t = t
    return best_t


def match_step_target(elements: list[dict], step: dict, require_keyword: bool = False) -> dict | None:
    """用步骤关键词在识别到的控件中找目标

    require_keyword=True 时只接受关键词命中（UIA 精确坐标场景）：
    UIA 控件是有名字的真实控件，靠类型猜测很容易框到标题栏按钮，宁可不标也不标错。
    """
    if not elements:
        return None
    keywords = [k.lower() for k in step.get("keywords", []) if k]
    type_hint = (step.get("type_hint") or "").lower()

    # 1) 关键词命中（越长越优先）
    scored: list[tuple[int, dict]] = []
    for el in elements:
        name = (el.get("name") or "").lower()
        if not name:
            continue
        for kw in keywords:
            if kw in name or name in kw:
                scored.append((len(kw), el))
                break
    if scored:
        scored.sort(key=lambda x: (x[0], float(x[1].get("confidence", 0))), reverse=True)
        return scored[0][1]

    if require_keyword:
        return None

    # 2) 类型兜底
    if type_hint:
        same_type = [e for e in elements
                     if type_hint in (e.get("control_type") or "").lower()]
        if same_type:
            same_type.sort(key=lambda e: float(e.get("confidence", 0)), reverse=True)
            return same_type[0]
    return None
