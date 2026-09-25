"""What a post is, independent of how it looks.

A post is a format, a title and hook, and a run of cards. A card is one slide's
content; the renderer decides how it is drawn. Keeping the two apart is what
lets four formats share four looks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

FORMATS = ("gallery", "ranking", "manual", "compat")

# What the format is called on the slide itself.
FORMAT_LABELS = {
    "gallery": "16TYPES",
    "ranking": "RANKING",
    "manual": "取扱説明書",
    "compat": "相性診断",
}


@dataclass(frozen=True, slots=True)
class Item:
    """One type's entry: a line that sells it and a line that explains it."""

    type: str
    title: str = ""
    body: str = ""
    rank: int = 0


@dataclass(frozen=True, slots=True)
class Card:
    kind: str  # cover | entry | grid | section | pair | closer
    title: str = ""
    body: str = ""
    label: str = ""
    number: int = 0
    total: int = 0
    items: tuple[Item, ...] = ()
    chips: tuple[str, ...] = ()
    types: tuple[str, ...] = ()  # the characters that appear on the card

    def to_dict(self) -> dict:
        data = asdict(self)
        data["items"] = [asdict(item) for item in self.items]
        data["chips"] = list(self.chips)
        data["types"] = list(self.types)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        return cls(
            kind=data["kind"],
            title=data.get("title", ""),
            body=data.get("body", ""),
            label=data.get("label", ""),
            number=int(data.get("number", 0)),
            total=int(data.get("total", 0)),
            items=tuple(Item(**item) for item in data.get("items", [])),
            chips=tuple(data.get("chips", [])),
            types=tuple(data.get("types", [])),
        )


@dataclass(slots=True)
class Post:
    seq: int
    format: str
    post_date: str
    title: str
    hook: str
    topic: str = ""  # gallery / ranking situation
    focus: str = ""  # the MBTI type a manual or compat post is about
    angle: str = ""  # 恋愛 / 友達 / 仕事 ...
    hashtags: tuple[str, ...] = ()
    cards: list[Card] = field(default_factory=list)
    # A run of posts that share a subject: one角度 of the manual walked across
    # the sixteen types, or one old theme. Everything in a series is drawn the
    # same way - same look, same palette, same arrangement - and goes out
    # 01 to 16 without anything else cutting in.
    series: str = ""
    series_index: int = 0  # which series this is, counting from the first
    series_position: int = 0  # 1..16 within the series, 0 for a one-off
    source: str = "llm"  # "llm" or "template", for spotting a run that fell back
    # Stock rather than the day's work: the old themed carousels, redrawn in the
    # current design. It goes out only when nothing freshly written is waiting.
    filler: bool = False

    @property
    def key(self) -> str:
        """An ASCII, sortable id; it becomes a folder name and part of a public URL.

        Filler is numbered in its own L series, so converting the back catalogue
        never collides with the daily numbers and the two stay tellable apart in
        a folder listing.
        """
        return f"L{self.seq:04d}-{self.format}" if self.filler else f"{self.seq:05d}-{self.format}"

    @property
    def description(self) -> str:
        cta = {
            "gallery": "あなたのタイプはどうだった？コメントで教えて",
            "ranking": "自分のタイプは何位だった？コメントで教えて",
            "manual": "当てはまったら保存して、その人に送ってみて",
            "compat": "相手のタイプと照らし合わせてみて",
        }[self.format]
        return f"{self.hook}\n\n{cta}\n\n{' '.join(self.hashtags)}"

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "key": self.key,
            "format": self.format,
            "post_date": self.post_date,
            "title": self.title,
            "hook": self.hook,
            "topic": self.topic,
            "focus": self.focus,
            "angle": self.angle,
            "hashtags": list(self.hashtags),
            "series": self.series,
            "series_index": self.series_index,
            "series_position": self.series_position,
            "source": self.source,
            "filler": self.filler,
            "cards": [card.to_dict() for card in self.cards],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        return cls(
            seq=int(data["seq"]),
            format=data["format"],
            post_date=data.get("post_date", ""),
            title=data["title"],
            hook=data.get("hook", ""),
            topic=data.get("topic", ""),
            focus=data.get("focus", ""),
            angle=data.get("angle", ""),
            hashtags=tuple(data.get("hashtags", [])),
            cards=[Card.from_dict(card) for card in data.get("cards", [])],
            series=data.get("series", ""),
            series_index=int(data.get("series_index", 0)),
            series_position=int(data.get("series_position", 0)),
            source=data.get("source", "llm"),
            filler=bool(data.get("filler", False)),
        )


# A post of one of these formats is about the sixteen types, so all sixteen
# have to be in it - each with a slide of its own.
EVERY_TYPE = ("gallery", "ranking")


def verify(post: Post, types: tuple[str, ...]) -> None:
    """Raise unless the post holds what its format promises.

    A ranking with twelve of its types sharing three slides passed every other
    check: the copy was complete and the slide count matched the cards. What it
    did not do was give each type a picture, which is the thing the format is
    for.
    """
    if post.format not in EVERY_TYPE:
        return
    entries = [card for card in post.cards if card.kind == "entry"]
    subjects = [card.types[0] for card in entries if card.types]
    missing = [mbti for mbti in types if mbti not in subjects]
    if missing:
        raise ValueError(f"{post.key}: no slide of its own for {', '.join(missing)}")
    repeated = [mbti for mbti in set(subjects) if subjects.count(mbti) > 1]
    if repeated:
        raise ValueError(f"{post.key}: {', '.join(sorted(repeated))} appears on more than one slide")
    if len(entries) != len(types):
        raise ValueError(f"{post.key}: {len(entries)} slides for {len(types)} types")
    cover = next((card for card in post.cards if card.kind == "cover"), None)
    if cover is not None and set(cover.types) != set(types):
        raise ValueError(f"{post.key}: the cover shows {len(set(cover.types))} of {len(types)} types")
