"""
Manim scene that animates the poc_va_macdha model pipeline.

Run a quick preview:
    source .venv/bin/activate
    python -m manim -pql visuals/model_pipeline.py ModelPipeline

Render a high-quality video:
    python -m manim -pqh visuals/model_pipeline.py ModelPipeline

To preview the last frame as a PNG:
    python -m manim -s visuals/model_pipeline.py ModelPipeline
"""

from manim import *

# Brand / desk tokens from apps/trade-desk/src/app/globals.css
BACKGROUND = ManimColor("#0B1014")
BRAND = ManimColor("#3d8f9c")
PASS = ManimColor("#2ecc87")
NEUTRAL = ManimColor("#7a8ba3")
FAIL = ManimColor("#e85d5d")
INK_100 = ManimColor("#f1f5f9")
INK_300 = ManimColor("#c5d0e0")
INK_400 = ManimColor("#93a4bb")

MODEL_NAME = "poc_va_macdha"


class ModelPipeline(Scene):
    def construct(self):
        self.camera.background_color = BACKGROUND

        title = Text("Model pipeline", font_size=36, color=INK_100)
        title.to_edge(UP, buff=0.6)

        model_label = Text(MODEL_NAME, font_size=20, color=INK_400)
        model_label.next_to(title, DOWN, buff=0.15)

        self.play(Write(title), Write(model_label), run_time=0.8)
        self.wait(0.2)

        stages = [
            ("OHLCV", "price · volume · ATR", PASS),
            ("VA / POC", "POC · VAL · VAH", PASS),
            ("HTF HA", "St.MACD-HA trend", PASS),
            ("Rule", "setup candidate / side", PASS),
            ("Filters", "VWAP · vol · red-flag · squeeze", PASS),
            ("Risk", "Kelly / sleeve sizing", PASS),
            ("Meta", "XGB hit probability", NEUTRAL),
            ("Action", "verdict + size", PASS),
        ]

        node_groups = []
        for label, sub, color in stages:
            rect = RoundedRectangle(
                width=2.1,
                height=1.0,
                corner_radius=0.08,
                stroke_color=color,
                stroke_width=2,
                fill_color=color,
                fill_opacity=0.12,
            )

            label_text = Text(label, font_size=18, color=INK_100)
            sub_text = Text(sub, font_size=13, color=INK_300)
            sub_text_group = VGroup(label_text, sub_text)
            sub_text_group.arrange(DOWN, buff=0.08, aligned_edge=ORIGIN)
            sub_text_group.move_to(rect.get_center())

            group = VGroup(rect, sub_text_group)
            node_groups.append(group)

        # Arrange nodes left-to-right with a small gap
        for i, group in enumerate(node_groups):
            if i == 0:
                group.to_edge(LEFT, buff=0.5)
                group.shift(DOWN * 0.3)
            else:
                group.next_to(node_groups[i - 1], RIGHT, buff=0.35)

        # Animate each node and the arrow to the next
        for i, group in enumerate(node_groups):
            rect = group[0]
            texts = group[1]
            self.play(Create(rect, run_time=0.5))
            self.play(Write(texts, run_time=0.5))

            if i < len(node_groups) - 1:
                next_group = node_groups[i + 1]
                arrow = Arrow(
                    start=rect.get_right(),
                    end=next_group[0].get_left(),
                    color=INK_400,
                    stroke_width=2,
                    buff=0.05,
                    max_tip_length_to_length_ratio=0.12,
                    tip_length=0.12,
                )
                self.play(Create(arrow, run_time=0.3))

        self.wait(1.5)

        # Highlight that the action stage is the only terminal output
        action_group = node_groups[-1]
        action_rect = action_group[0]
        pulse = RoundedRectangle(
            width=action_rect.width + 0.15,
            height=action_rect.height + 0.15,
            corner_radius=0.12,
            stroke_color=PASS,
            stroke_width=3,
            fill_color=PASS,
            fill_opacity=0.05,
        )
        pulse.move_to(action_rect.get_center())
        self.play(Create(pulse, run_time=0.6))
        self.wait(1)
