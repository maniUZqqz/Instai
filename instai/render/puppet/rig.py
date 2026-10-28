"""Character rig: layered parts with pivots, a parent hierarchy and a z-order.

Part image coordinates are pixels of the part's own PNG; `pivot` is the joint (in that PNG) and `pos` is where the joint sits in the
parent's coordinate space (the parent's own PNG pixels; for root parts: the character's design canvas). Parts of one `group`
(mouth, eyes, brows) are alternatives: exactly one `state` of the group is visible at a time.

Spec (JSON, stored in CharacterRig.spec):
  {"version": 1, "size": [w, h], "anchor": [x, y],
   "parts": {"body": {"image": "rel/or/abs.png", "pivot": [x, y], "pos": [x, y], "z": 10, "parent": null, "group": null, "state": null}, ...}}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import geometry as g

MOUTH_SHAPES = "ABCDEFGHX"                   # Rhubarb's mouth shapes
# when a rig lacks a mouth shape, the nearest drawn one is used
MOUTH_FALLBACK = {"A": ["X"], "B": ["A", "X"], "C": ["B", "D", "A"], "D": ["C", "B", "A"], "E": ["C", "B", "A"], "F": ["E", "C", "B", "A"],
                  "G": ["B", "A"], "H": ["C", "B", "A"], "X": ["A", "B"]}
GROUP_DEFAULT = {"mouth": "X", "eyes": "open", "brows": "neutral"}
Z_DEFAULT = {"prop_back": 1, "leg_l": 5, "leg_r": 6, "body": 10, "arm_l": 12, "head": 20, "eyes": 21, "brows": 22, "mouth": 23, "arm_r": 30,
             "prop": 40}


def default_z(name: str) -> int:
    return Z_DEFAULT.get(name, Z_DEFAULT.get(name.split("_")[0], 10))


class RigError(ValueError):
    pass


@dataclass
class Part:
    name: str
    image: str
    pivot: tuple[float, float] = (0.0, 0.0)
    pos: tuple[float, float] = (0.0, 0.0)
    z: int = 10
    parent: str | None = None
    group: str | None = None
    state: str | None = None
    size: tuple[int, int] = (0, 0)


@dataclass
class Rig:
    size: tuple[int, int]
    anchor: tuple[float, float]
    parts: dict[str, Part] = field(default_factory=dict)
    version: int = 1

    # ---------------------------------------------------------------- build / validate
    @classmethod
    def from_spec(cls, spec: dict, media_root: Path | None = None, *, load_sizes: bool = True) -> "Rig":
        if not isinstance(spec, dict) or not spec.get("parts"):
            raise RigError("the rig has no parts")
        size = tuple(spec.get("size") or (1024, 1024))
        rig = cls(size=(int(size[0]), int(size[1])), anchor=tuple(spec.get("anchor") or (size[0] / 2, size[1] * 0.97)), version=int(spec.get("version", 1)))
        for name, p in spec["parts"].items():
            img = str(p.get("image") or "")
            if media_root is not None and img and not Path(img).is_absolute():
                img = str(media_root / img)
            part = Part(name=name, image=img, pivot=tuple(p.get("pivot") or (0, 0)), pos=tuple(p.get("pos") or (0, 0)),
                        z=int(p.get("z", default_z(name))), parent=p.get("parent"), group=p.get("group"), state=p.get("state"))
            if load_sizes and img:
                try:
                    from PIL import Image

                    with Image.open(img) as im:
                        part.size = im.size
                except OSError as e:
                    raise RigError(f"part {name}: image not readable ({Path(img).name})") from e
            rig.parts[name] = part
        rig.validate()
        return rig

    def validate(self) -> None:
        for p in self.parts.values():
            if p.parent is not None and p.parent not in self.parts:
                raise RigError(f"part {p.name}: unknown parent {p.parent}")
        for p in self.parts.values():  # cycles
            seen, cur = set(), p
            while cur.parent is not None:
                if cur.name in seen:
                    raise RigError(f"parent loop at {cur.name}")
                seen.add(cur.name)
                cur = self.parts[cur.parent]
        if not any(p.parent is None for p in self.parts.values()):
            raise RigError("no root part")

    def to_spec(self, media_root: Path | None = None) -> dict:
        def rel(img: str) -> str:
            try:
                return str(Path(img).relative_to(media_root)).replace("\\", "/") if media_root else img
            except ValueError:
                return img

        return {"version": self.version, "size": list(self.size), "anchor": list(self.anchor),
                "parts": {n: {"image": rel(p.image), "pivot": list(p.pivot), "pos": list(p.pos), "z": p.z, "parent": p.parent, "group": p.group,
                              "state": p.state} for n, p in self.parts.items()}}

    # ---------------------------------------------------------------- queries
    def groups(self) -> dict[str, dict[str, Part]]:
        out: dict[str, dict[str, Part]] = {}
        for p in self.parts.values():
            if p.group and p.state:
                out.setdefault(p.group, {})[p.state] = p
        return out

    def mouth_shapes(self) -> list[str]:
        return sorted(self.groups().get("mouth", {}))

    def choose_state(self, group: str, wanted: str) -> str | None:
        """The state of `group` to show for `wanted` (with the mouth fallback chain), or None when the group does not exist."""
        states = self.groups().get(group)
        if not states:
            return None
        if wanted in states:
            return wanted
        for alt in MOUTH_FALLBACK.get(wanted, []) if group == "mouth" else []:
            if alt in states:
                return alt
        default = GROUP_DEFAULT.get(group)
        return default if default in states else sorted(states)[0]

    def chain(self, name: str) -> list[Part]:
        """root -> ... -> part."""
        out, cur = [], self.parts[name]
        while True:
            out.append(cur)
            if cur.parent is None:
                break
            cur = self.parts[cur.parent]
        return out[::-1]

    def world_matrices(self, base: g.Matrix, pose: dict[str, tuple[float, float, float, float, float]]) -> dict[str, g.Matrix]:
        """World matrix of every part. `pose[name]` = (dx, dy, rot_deg, sx, sy) in the part's parent space (design px); `base` places the
        whole character on the canvas. Animation turns the part about its own pivot, children follow."""
        mats: dict[str, g.Matrix] = {}

        def world(name: str) -> g.Matrix:
            if name in mats:
                return mats[name]
            p = self.parts[name]
            parent = world(p.parent) if p.parent else base
            dx, dy, rot, sx, sy = pose.get(name, (0.0, 0.0, 0.0, 1.0, 1.0))
            local = g.mul(g.translate(p.pos[0] + dx, p.pos[1] + dy), g.mul(g.rotate(rot), g.mul(g.scale(sx, sy), g.translate(-p.pivot[0], -p.pivot[1]))))
            mats[name] = g.mul(parent, local)
            return mats[name]

        for n in self.parts:
            world(n)
        return mats

    def visible_parts(self, mouth: str, eyes: str = "open", brows: str | None = None) -> list[Part]:
        """Parts to draw, back to front, with one state per group."""
        want = {"mouth": mouth, "eyes": eyes, "brows": brows or GROUP_DEFAULT["brows"]}
        chosen = {grp: self.choose_state(grp, w) for grp, w in want.items()}
        out = []
        for p in self.parts.values():
            if p.group:
                if p.group in chosen and chosen[p.group] != p.state:
                    continue
            if p.image:
                out.append(p)
        return sorted(out, key=lambda p: (p.z, p.name))
