import copy
import random
import time
from typing import Iterable, List

try:
    from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
    from matplotlib import animation
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ModuleNotFoundError:
    Line3DCollection = Poly3DCollection = None  # type: ignore[assignment]
    animation = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    HAS_MPL = False

from py3dbp import Bin, Item, Packer

# ---------- CONFIG ----------
BIN_NAME = "bin-full-util"
BIN_WHD = (10, 5, 10)  # (W, H, D)
BIN_MAX_WEIGHT = 99999
BIN_CANTILEVER = 0
BIN_PUT_TYPE = 0

N_ITEMS = 25
ITEMS_MODE = "tiling"  # "tiling" | "random" | "manual"
SEED = 42
RAND_W_RANGE = (2, 6)
RAND_H_RANGE = (2, 5)
RAND_D_RANGE = (2, 6)
RANDOM_WEIGHT_RANGE = (1, 10)

SUPPORT_SURFACE_RATIO = 0.75
NUMBER_OF_DECIMALS = 0
BIGGER_FIRST = True
INTERVAL_MS = 350
FPS_GIF = 3

# Example manual mode items (list of tuples of width, height, depth, weight, color)
MANUAL_ITEMS = [
    (6, 2, 2, 6, "gold"),
    (4, 3, 3, 7, "skyblue"),
    (2, 2, 6, 5, "olive"),
]

COLORS = [
    "gold",
    "skyblue",
    "lightgreen",
    "tomato",
    "violet",
    "orange",
    "olive",
    "pink",
    "brown",
    "plum",
    "khaki",
    "deepskyblue",
    "palegreen",
    "salmon",
    "orchid",
    "darkorange",
    "yellowgreen",
    "hotpink",
    "peru",
    "mediumpurple",
    "turquoise",
    "wheat",
    "lightcoral",
    "steelblue",
    "tan",
]

snapshots: List[List[Item]] = []
_original_putItem = None


# ---------- Helpers ----------
def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _box_vertices(x, y, z, dx, dy, dz):
    return [
        (x, y, z),
        (x + dx, y, z),
        (x + dx, y + dy, z),
        (x, y + dy, z),
        (x, y, z + dz),
        (x + dx, y, z + dz),
        (x + dx, y + dy, z + dz),
        (x, y + dy, z + dz),
    ]


def _box_faces_from_vertices(p):
    return [
        [p[0], p[1], p[2], p[3]],
        [p[4], p[5], p[6], p[7]],
        [p[0], p[1], p[5], p[4]],
        [p[2], p[3], p[7], p[6]],
        [p[1], p[2], p[6], p[5]],
        [p[3], p[0], p[4], p[7]],
    ]


def draw_wire_bin(ax, W, H, D):
    p = _box_vertices(0, 0, 0, W, H, D)
    edges = [
        [p[0], p[1]],
        [p[1], p[2]],
        [p[2], p[3]],
        [p[3], p[0]],
        [p[4], p[5]],
        [p[5], p[6]],
        [p[6], p[7]],
        [p[7], p[4]],
        [p[0], p[4]],
        [p[1], p[5]],
        [p[2], p[6]],
        [p[3], p[7]],
    ]
    lc = Line3DCollection(edges, colors="k", linewidths=1.3)
    ax.add_collection3d(lc)
    return [lc]


def draw_box(
    ax,
    x,
    y,
    z,
    dx,
    dy,
    dz,
    facecolor=(0.6, 0.7, 0.9),
    edgecolor="k",
    label=None,
    alpha=0.65,
):
    faces = _box_faces_from_vertices(_box_vertices(x, y, z, dx, dy, dz))
    poly = Poly3DCollection(faces, facecolors=facecolor, edgecolors=edgecolor, linewidths=0.6)
    poly.set_alpha(alpha)
    ax.add_collection3d(poly)
    txt = None
    if label:
        cx, cy, cz = x + dx / 2, y + dy / 2, z + dz / 2
        txt = ax.text(cx, cy, cz, label, fontsize=7, ha="center", va="center")
    return [poly] + ([txt] if txt else [])


# ---------- Snapshot capture ----------
def _patched_putItem(self: Bin, item: Item, pivot, axis=None):
    before = len(self.items)
    res = _original_putItem(self, item, pivot, axis)
    after = len(self.items)
    if res and after > before:
        snapshots.append([copy.deepcopy(it) for it in self.items])
    return res


# ---------- Item builders ----------
def gen_random_item(idx: int, bin_w: int, bin_h: int, bin_d: int):
    w = clamp(random.randint(*RAND_W_RANGE), 1, int(bin_w))
    h = clamp(random.randint(*RAND_H_RANGE), 1, int(bin_h))
    d = clamp(random.randint(*RAND_D_RANGE), 1, int(bin_d))
    weight = random.randint(*RANDOM_WEIGHT_RANGE)
    color = COLORS[idx % len(COLORS)]
    return dict(
        partno=f"Box-{idx + 1}",
        name="auto",
        typeof="cube",
        WHD=(w, h, d),
        weight=weight,
        level=idx + 1,
        loadbear=9999,
        updown=False,
        color=color,
    )


def gen_tiling_items(bin_w: int, bin_h: int, bin_d: int) -> Iterable[dict]:
    cell_w = 2
    cell_d = 2
    cols = bin_w // cell_w
    rows = bin_d // cell_d
    if cols * rows < N_ITEMS:
        raise ValueError("Bin footprint is too small for tiling layout")

    # heights chosen so that volume utilisation ≈ 92% in a 10x5x10 bin
    heights = [
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        4,
        4,
        4,
        4,
        4,
        4,
        4,
        4,
        4,
        5,
        5,
    ]
    if len(heights) != N_ITEMS:
        raise ValueError("Tiling heights list must match N_ITEMS")

    for idx in range(N_ITEMS):
        color = COLORS[idx % len(COLORS)]
        yield dict(
            partno=f"Tile-{idx + 1}",
            name="tiling",
            typeof="cube",
            WHD=(cell_w, heights[idx], cell_d),
            weight=2,
            level=idx + 1,
            loadbear=9999,
            updown=False,
            color=color,
        )


def gen_manual_items() -> Iterable[dict]:
    items = list(MANUAL_ITEMS)
    if len(items) < N_ITEMS:
        random.seed(SEED)
        while len(items) < N_ITEMS:
            w = clamp(random.randint(*RAND_W_RANGE), 1, BIN_WHD[0])
            h = clamp(random.randint(*RAND_H_RANGE), 1, BIN_WHD[1])
            d = clamp(random.randint(*RAND_D_RANGE), 1, BIN_WHD[2])
            weight = random.randint(*RANDOM_WEIGHT_RANGE)
            items.append((w, h, d, weight, COLORS[len(items) % len(COLORS)]))
    for idx, (w, h, d, weight, color) in enumerate(items[:N_ITEMS]):
        yield dict(
            partno=f"Manual-{idx + 1}",
            name="manual",
            typeof="cube",
            WHD=(w, h, d),
            weight=weight,
            level=idx + 1,
            loadbear=9999,
            updown=True,
            color=color,
        )


def build_items(bin_w: int, bin_h: int, bin_d: int) -> List[dict]:
    if ITEMS_MODE == "tiling":
        return list(gen_tiling_items(bin_w, bin_h, bin_d))
    if ITEMS_MODE == "manual":
        return list(gen_manual_items())

    random.seed(SEED)
    return [gen_random_item(i, bin_w, bin_h, bin_d) for i in range(N_ITEMS)]


# ---------- Main ----------
def main():
    global _original_putItem
    snapshots.clear()
    start = time.time()

    packer = Packer()
    bW, bH, bD = map(int, BIN_WHD)
    bin_obj = Bin(BIN_NAME, (bW, bH, bD), BIN_MAX_WEIGHT, BIN_CANTILEVER, BIN_PUT_TYPE)
    packer.addBin(bin_obj)

    items_conf = build_items(bW, bH, bD)
    for cfg in items_conf:
        packer.addItem(Item(**cfg))

    _original_putItem = Bin.putItem
    Bin.putItem = _patched_putItem

    packer.items.sort(key=lambda x: x.width * x.height * x.depth, reverse=True)

    packer.pack(
        bigger_first=BIGGER_FIRST,
        distribute_items=False,
        fix_point=True,
        check_stable=True,
        support_surface_ratio=SUPPORT_SURFACE_RATIO,
        number_of_decimals=NUMBER_OF_DECIMALS,
    )
    packer.putOrder()

    Bin.putItem = _original_putItem

    used = time.time() - start
    b = packer.bins[0]
    vol_bin = b.width * b.height * b.depth
    vol_fit = sum(it.width * it.height * it.depth for it in b.items)
    util = 100.0 * float(vol_fit) / float(vol_bin) if vol_bin else 0.0
    print(
        f"Packed in {used:.3f}s, frames={len(snapshots)}; "
        f"fitted={len(b.items)}, unfitted={len(b.unfitted_items)}, "
        f"utilization={util:.2f}%"
    )

    if not HAS_MPL:
        print("Matplotlib not installed; skipping animation rendering.")
        return

    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="3d")

    W, H, D = float(b.width), float(b.height), float(b.depth)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_zlim(0, D)
    ax.set_xlabel("X (width)")
    ax.set_ylabel("Y (height)")
    ax.set_zlabel("Z (depth)")
    try:
        ax.set_box_aspect((W, H, D))
    except Exception:
        pass
    ax.set_title(f"Packing animation - {b.partno} / util≈{util:.1f}%")

    artists_bin = draw_wire_bin(ax, W, H, D)
    artists_items: List = []

    def clear_items():
        nonlocal artists_items
        for art in artists_items:
            try:
                art.remove()
            except Exception:
                pass
        artists_items = []

    def frame(i):
        clear_items()
        items = snapshots[i]
        for it in items:
            w, h, d = it.getDimension()
            x, y, z = it.position
            c = getattr(it, "color", None) or (0.6, 0.7, 0.9)
            label = f"{it.partno}\n{int(w)}×{int(h)}×{int(d)}"
            arts = draw_box(
                ax,
                float(x),
                float(y),
                float(z),
                float(w),
                float(h),
                float(d),
                facecolor=c,
                edgecolor="k",
                label=label,
                alpha=0.72,
            )
            artists_items.extend(arts)
        txt = ax.text(0, -0.14 * H, D, f"Placed: {len(items)}/{len(b.items)}", fontsize=10)
        artists_items.append(txt)
        return artists_items + artists_bin

    if len(snapshots) > 0:
        anim = animation.FuncAnimation(
            fig,
            frame,
            frames=len(snapshots),
            interval=INTERVAL_MS,
            blit=False,
            repeat=False,
        )
        try:
            from matplotlib.animation import PillowWriter

            anim.save("packing_animation_full_util.gif", writer=PillowWriter(fps=FPS_GIF))
            print("Saved GIF: packing_animation_full_util.gif")
        except Exception as e:
            print("GIF export failed:", e)
            try:
                Writer = animation.writers["ffmpeg"]
                writer = Writer(fps=10, metadata=dict(artist="py3dbp"), bitrate=1800)
                anim.save("packing_animation_full_util.mp4", writer=writer)
                print("Saved MP4: packing_animation_full_util.mp4")
            except Exception as e2:
                print("MP4 export failed:", e2)
                print("Install pillow or ffmpeg to enable animation exports.")

    plt.show()


if __name__ == "__main__":
    main()
