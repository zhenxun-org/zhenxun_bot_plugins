from typing import Dict, List, Optional, Union
import random
import matplotlib as mpl


def get_all_colormaps() -> Dict[str, List[str]]:
    """获取所有可用的颜色映射，按类别分组"""
    all_cmaps = list(mpl.colormaps)

    cmap_categories = {
        "感知均匀顺序色图": ["viridis", "plasma", "inferno", "magma", "cividis"],
        "顺序色图": [
            "Greys",
            "Purples",
            "Blues",
            "Greens",
            "Oranges",
            "Reds",
            "YlOrBr",
            "YlOrRd",
            "OrRd",
            "PuRd",
            "RdPu",
            "BuPu",
            "GnBu",
            "PuBu",
            "YlGnBu",
            "PuBuGn",
            "BuGn",
            "YlGn",
        ],
        "顺序色图2": [
            "binary",
            "gist_yarg",
            "gist_gray",
            "gray",
            "bone",
            "pink",
            "spring",
            "summer",
            "autumn",
            "winter",
            "cool",
            "Wistia",
            "hot",
            "afmhot",
            "gist_heat",
            "copper",
        ],
        "发散色图": [
            "PiYG",
            "PRGn",
            "BrBG",
            "PuOr",
            "RdGy",
            "RdBu",
            "RdYlBu",
            "RdYlGn",
            "Spectral",
            "coolwarm",
            "bwr",
            "seismic",
            "berlin",
            "managua",
            "vanimo",
        ],
        "循环色图": ["twilight", "twilight_shifted", "hsv"],
        "定性色图": [
            "Pastel1",
            "Pastel2",
            "Paired",
            "Accent",
            "Dark2",
            "Set1",
            "Set2",
            "Set3",
            "tab10",
            "tab20",
            "tab20b",
            "tab20c",
        ],
        "其他色图": [
            "flag",
            "prism",
            "ocean",
            "gist_earth",
            "terrain",
            "gist_stern",
            "gnuplot",
            "gnuplot2",
            "CMRmap",
            "cubehelix",
            "brg",
            "gist_rainbow",
            "rainbow",
            "jet",
            "turbo",
            "nipy_spectral",
            "gist_ncar",
        ],
    }

    categorized_cmaps = []
    for cmaps in cmap_categories.values():
        categorized_cmaps.extend(cmaps)

    uncategorized = [cmap for cmap in all_cmaps if cmap not in categorized_cmaps]
    if uncategorized:
        cmap_categories["未分类"] = uncategorized

    return cmap_categories


def get_recommended_colormaps() -> List[str]:
    """获取推荐的颜色映射列表"""
    return [
        "viridis",
        "plasma",
        "inferno",
        "magma",
        "cividis",
        "Blues",
        "Greens",
        "Reds",
        "Purples",
        "Oranges",
        "RdBu",
        "coolwarm",
        "PiYG",
        "PRGn",
        "RdYlBu",
        "turbo",
        "gist_earth",
        "ocean",
        "terrain",
        "CMRmap",
    ]


def get_dark_bg_colormaps() -> List[str]:
    """获取适合黑色背景的颜色映射列表"""
    return [
        "plasma",
        "hot",
        "YlOrRd",
        "YlOrBr",
        "Oranges",
        "OrRd",
        "rainbow",
        "jet",
        "turbo",
        "gist_rainbow",
        "coolwarm",
        "RdBu",
        "Spectral",
        "autumn",
        "summer",
        "spring",
        "winter",
        "copper",
    ]


def get_white_bg_colormaps() -> List[str]:
    """获取适合白色背景的颜色映射列表"""
    return [
        "viridis",
        "plasma",
        "inferno",
        "magma",
        "cividis",
        "Blues",
        "Greens",
        "Reds",
        "Purples",
        "BuPu",
        "GnBu",
        "RdBu",
        "coolwarm",
        "PiYG",
        "PRGn",
        "RdYlBu",
        "ocean",
        "terrain",
        "gist_earth",
        "CMRmap",
        "cubehelix",
    ]


def get_random_colormap(category: Optional[str] = None) -> str:
    """获取随机的颜色映射，可指定类别"""
    cmap_categories = get_all_colormaps()

    if category and category in cmap_categories:
        return random.choice(cmap_categories[category])

    return random.choice(get_recommended_colormaps())


def get_colormap_category(colormap_name: str) -> str:
    """获取颜色映射的类别，未找到返回"未知类别" """
    cmap_categories = get_all_colormaps()

    for category, cmaps in cmap_categories.items():
        if colormap_name in cmaps:
            return category

    return "未知类别"


def resolve_colormap(colormap: Union[str, List[str]]) -> str:
    """解析颜色映射配置，列表则随机选择一个"""
    if isinstance(colormap, list):
        if not colormap:
            return "viridis"
        return random.choice(colormap)
    return colormap
