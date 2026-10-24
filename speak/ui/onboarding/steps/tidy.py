from ..common import AMBER, EXAMPLE_LITERAL, EXAMPLE_OFF, EXAMPLE_QUICK, EXAMPLE_SMART, MODEL_CHOICES, SAY, _ai_changes, _level, _seconds
from ..widgets import ChoiceCard, OptionGroup, Segmented
from ..stages import SpeedStage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .... import config, tidy
from ....benchmark import Result
from ....controller import FINISHING
from ...pages import SettingRow, _combo, _label
from ...widgets import Toggle

class TidyStep:
    def _tidy_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(12)
        heading, say = self._heading("Tidy up your words", f"You say  “{SAY}”")
        layout.addWidget(heading)
        layout.addWidget(say)

        self.tidy_options = OptionGroup(self)
        self.level_cards = {"off": ChoiceCard("Off", "Exactly as said", example=f"“{EXAMPLE_OFF}”"),
                            "fast": ChoiceCard("Quick", "Removes ums, instant", example=f"“{EXAMPLE_QUICK}”"),
                            "ai": ChoiceCard("Smart", "…", example="…")}
        for card in self.level_cards.values():
            card.setMinimumHeight(140)
        cards = self._cards(self.tidy_options, self.level_cards, self._on_level)
        layout.addWidget(cards)

        self.model_options = Segmented(MODEL_CHOICES, self._model)
        self.model_options.picked.connect(self._on_model)
        self.model_row = SettingRow("Model size", " ", self.model_options)
        self.device = _combo(config.CLEANUP_DEVICES, settings["cleanup_device"])
        self.device.currentIndexChanged.connect(
            lambda: self._config_changed({"cleanup_device": self.device.currentData()}))
        self.device_row = SettingRow("Runs on", " ", self.device)
        self.corrections = Toggle()
        self.corrections.setChecked(settings["corrections"])
        self.corrections.toggled.connect(lambda on: self._config_changed({"corrections": on}))
        self.corrections_row = SettingRow("Fix changes of mind", " ", self.corrections)
        self.options_card = self._settings_card(self.model_row, self.device_row, self.corrections_row)
        layout.addWidget(self.options_card)

        layout.addWidget(self._speed_strip())
        layout.addStretch(1)
        self._reveals[self.TIDY] = [heading, say, *self.level_cards.values(), self.options_card, self.speed_card]
        return step


    def _speed_strip(self) -> QFrame:
        """Fixed-size card: the indicator playing the test on top, buttons left and the result right."""
        self.speed_card = QFrame(objectName="card")
        card = QVBoxLayout(self.speed_card)
        card.setContentsMargins(18, 12, 18, 12)
        card.setSpacing(8)
        self.test_stage = SpeedStage()
        self.latency_label = QLabel("")
        self.latency_label.setFixedSize(100, 34)
        self.latency_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.latency_label.setStyleSheet("font-size: 20pt; font-weight: 700;")
        self.verdict_label = _label(self.SPEED_IDLE, "hint")
        self.verdict_label.setFixedSize(60, 34)
        self.verdict_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sample_button = QPushButton("Test speed", objectName="primary", cursor=Qt.PointingHandCursor)
        self.sample_button.setToolTip("Time a bundled sample recording")
        self.sample_button.clicked.connect(self._start_test)
        self.details_button = QPushButton("Details", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.details_button.clicked.connect(self._toggle_details)
        policy = self.details_button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.details_button.setSizePolicy(policy)
        self.details_button.hide()
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.sample_button)
        row.addWidget(self.details_button)
        row.addWidget(self.test_stage, 1)
        row.addWidget(self.verdict_label)
        row.addWidget(self.latency_label)
        card.addLayout(row)

        self.details_box = QWidget()
        details = QVBoxLayout(self.details_box)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(4)
        self.text_label = _label("", "hint")
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_label = _label("", "hint")
        details.addWidget(self.text_label)
        details.addWidget(self.details_label)
        self.details_box.hide()
        card.addWidget(self.details_box)
        return self.speed_card


    def _on_level(self, key: str):
        self._config_changed({"tidy": key} if key != "ai" else _ai_changes(self._model))


    def _on_model(self, choice: str):
        self._model = choice
        self._config_changed(_ai_changes(choice))


    def _ai_plan(self) -> tidy.Plan:
        return tidy.plan({**self._tidy, **_ai_changes(self._model)})


    def _refresh_tidy(self):
        """Redraw everything that depends on the tidy choice: card texts, example, and which options apply."""
        level = _level(self._tidy)
        ai = self._ai_plan()
        large = ai.model_id == config.LARGE_MODEL
        where = "graphics card" if ai.device else "processor"
        name = "Large model" if large else "Small model"
        self.level_cards["ai"].set_texts(
            f"{name} · {where}",
            f"“{EXAMPLE_SMART if ai.llm_mode == 'smart' else EXAMPLE_LITERAL}”")
        for key, card in self.level_cards.items():
            card.blockSignals(True)
            card.setChecked(key == level)
            card.blockSignals(False)
        on = level == "ai"
        na = "Not used with Off or Quick"
        if self._model == "auto":
            model_hint = f"Picks what suits this computer: {name} on your {where}"
        elif self._model == "small":
            model_hint = "Quick on any computer. Punctuation and capitals only"
        elif large:
            model_hint = f"Best results. {'About half a second' if ai.device else 'A few seconds'} here"
        else:
            model_hint = "Not enough free memory for Large, so Small is used"
        self.model_options.set_value(self._model if on else "")
        self.model_row.hint.setText(model_hint if on else na)
        self.model_row.setEnabled(on)
        self.device_row.hint.setText("Your graphics card is faster when you have one" if on else na)
        self.device_row.setEnabled(on)
        fix = on and large
        self.corrections_row.hint.setText(
            "“Tuesday, no wait, Wednesday” becomes “Wednesday”" if fix else
            "Needs the Large model" if on else na)
        self.corrections_row.setEnabled(fix)
        # What can't apply reads as off, so a greyed-out switch never looks like an unchangeable "on".
        self.corrections.blockSignals(True)
        self.corrections.setChecked(bool(self._tidy["corrections"]) and fix)
        self.corrections.blockSignals(False)


    def _config_changed(self, change: dict):
        self._tidy.update(change)
        self._refresh_tidy()
        if self._testing:
            self._testing = False
            self.test_cancelled.emit()
        self.changed.emit(change)
        if self._tested:
            self._set_latency("")
            self.verdict_label.setText(self.SPEED_IDLE)
            self.test_stage.set_phase("preparing", "Updating")
            self._retest.start()


    def _set_latency(self, text: str, color: str = None):
        self.latency_label.setText(text)
        self.latency_label.setStyleSheet(
            "font-size: 20pt; font-weight: 700;" + (f" color: {color};" if color else ""))


    def _retest_now(self):
        self._start_test()


    def _cancel_test(self):
        """Stop whatever the speed strip is doing and put it back to its starting state."""
        self._retest.stop()
        if self._testing:
            self._testing = False
            self.test_cancelled.emit()
        self._tested = False
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("idle")
        self.details_box.hide()
        self.details_button.hide()
        self._set_busy(False)


    def _set_busy(self, busy: bool):
        self.sample_button.setEnabled(not busy)


    def _start_test(self):
        self._retest.stop()
        self._tested = True
        self._testing = True
        self._set_busy(True)
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("preparing", "Getting ready")
        self.details_box.hide()
        self.details_button.hide()
        self.test_requested.emit(None, 0)


    def set_progress(self, message: str, percent=None):
        if not self._testing:
            return
        if message.startswith("Listening"):
            self.test_stage.set_phase("listening")
        elif message.startswith("Tidying"):
            self.test_stage.set_phase("processing", FINISHING)
        else:
            self.test_stage.set_phase("preparing", f"{message} {int(percent)}%" if percent is not None else message)


    def set_result(self, result: Result):
        if not self._testing:  # a test that was cancelled or replaced while it ran
            return
        self._testing = False
        self._set_busy(False)
        rating, _ = result.verdict
        pal = self.palette_
        color = {"good": pal.success, "ok": AMBER, "slow": pal.danger}[rating]
        self._set_latency(_seconds(result.latency_s), color)
        word = {"good": "Fast", "ok": "Good", "slow": "Slow"}[rating]
        self.verdict_label.setText(word)
        self.test_stage.set_phase("done")
        text = " ".join(result.text.split())
        self.text_label.setText(f"“{text}”" if text else "No words recognised.")
        self.details_label.setText(self._details(result))
        self.details_button.show()


    def set_failure(self, message: str):
        if self._testing:
            self._testing = False
            self._fail(message)


    def _fail(self, message: str):
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("idle", message)
        self._set_busy(False)


    def _details(self, r: Result) -> str:
        plan = r.plan
        if plan.model_id:
            size = "Large" if plan.model_id == config.LARGE_MODEL else "Small"
            tidy_name = f"Smart · {size} model on your {'graphics card' if plan.device else 'processor'}"
        else:
            tidy_name = "Quick" if plan.level == "fast" else "Off"
        lines = [f"Speech {_seconds(r.transcribe_s)} + tidy-up {_seconds(r.tidy_s)} = {_seconds(r.latency_s)} wait",
                 f"Tidy-up: {tidy_name}"]
        if r.raw and " ".join(r.raw.split()) != " ".join(r.text.split()):
            lines.append(f"Before tidy-up: “{' '.join(r.raw.split())}”")
        return "<br>".join(lines)


    def _toggle_details(self):
        self.details_box.setVisible(not self.details_box.isVisible())
