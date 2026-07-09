from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

from .api_client import GameState
from .i18n import _

MAX_MESSAGES = 200


class HudFeed(QWidget):
    """HUD 消息滚动面板（带标题）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = QLabel(_("战况消息"))
        title.setStyleSheet(
            "color: #7ec8e3; font-weight: bold; font-size: 10px; padding: 2px 4px;")
        layout.addWidget(title)
        self._title_label = title

        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.document().setMaximumBlockCount(MAX_MESSAGES)
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setStyleSheet("""
            QTextEdit {
                background: #1a1a2e; border: 1px solid #3a3a5c; border-radius: 4px;
                color: #e0e0e0; font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 11px; padding: 4px;
            }
        """)
        layout.addWidget(self._edit)
        self._shown_ids: set[int] = set()

    def _retranslate(self):
        """语言切换时刷新标题。"""
        self._title_label.setText(_("战况消息"))

    def update_state(self, state: GameState):
        hud = state.hudmsg_raw
        if not hud:
            return
        for dmg in hud.get("damage", []):
            dmg_id = dmg.get("id", -1)
            if dmg_id not in self._shown_ids:
                self._shown_ids.add(dmg_id)
                self._add_message(dmg.get("msg", ""), dmg.get("enemy", False))

    def _add_message(self, msg: str, is_enemy: bool = False):
        color = "#e94560" if is_enemy else "#7ec8e3"
        self._edit.append(f'<span style="color:{color};">{msg}</span>')
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._edit.setTextCursor(cursor)
        self._edit.ensureCursorVisible()

    def clear_messages(self):
        self._shown_ids.clear()
        self._edit.clear()
