import sys
import json
import os
import time
import re
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QComboBox, QSpinBox, QMessageBox, QLineEdit, QTableWidget,QTableWidgetItem,
    QProgressBar,QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QClipboard, QKeySequence, QColor, QFont
from pynput.keyboard import Controller, Key
from global_hotkeys import register_hotkeys, start_checking_hotkeys, stop_checking_hotkeys

class TypingThread(QThread):
    progress = Signal(int)
    finished = Signal()

    def __init__(self, text, interval):
        super().__init__()
        self.text = text
        self.interval = interval
        self.keyboard_controller = Controller()
        self.is_running = True

    def run(self):
        print(self.interval)
        time.sleep(0.5)
        total_chars = len(self.text)
        for i, char in enumerate(self.text):
            if not self.is_running:
                break
            if char == '\n':
                self.keyboard_controller.press(Key.enter)
                self.keyboard_controller.release(Key.enter)
            else:
                self.keyboard_controller.press(char)
                self.keyboard_controller.release(char)
            time.sleep(self.interval)
            self.progress.emit(int((i + 1) / total_chars * 100))
        self.finished.emit()

    def stop(self):
        self.is_running = False

class HotKeyInput(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处并按下快捷键组合...")
        self._keys = set()
        self._last_key_sequence = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            self._keys.add(event.key())
        else:
            key = event.key()
            if key not in self._keys:
                self._keys.add(key)

        key_sequence = self._get_key_sequence()
        if key_sequence:
            self.setText(key_sequence)
            self._last_key_sequence = key_sequence

    def keyReleaseEvent(self, event):
        key = event.key()
        if key in self._keys:
            self._keys.remove(key)

    def _get_key_sequence(self):
        if not self._keys:
            return ""

        key_texts = []
        if Qt.Key_Control in self._keys:
            key_texts.append("control")
        if Qt.Key_Alt in self._keys:
            key_texts.append("Alt")
        if Qt.Key_Shift in self._keys:
            key_texts.append("Shift")
        if Qt.Key_Meta in self._keys:
            key_texts.append("Meta")

        for key in self._keys:
            if key not in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
                key_text = QKeySequence(key).toString()
                if key_text and key_text not in key_texts:
                    key_texts.append(key_text)

        return "+".join(key_texts)

    def get_key_sequence(self):
        return self._last_key_sequence

class HotkeyManager:
    def __init__(self):
        self.hotkey = None
        self.callback = None

    def set_hotkey(self, hotkey_str, callback):
        self.callback = callback
        self.hotkey = hotkey_str

    def register_global_hotkey(self):
        if self.hotkey and self.callback:
            bindings = [
                [self.hotkey, None, self.callback, False]
            ]
            register_hotkeys(bindings)
            start_checking_hotkeys()

class ClipboardHistory:
    def __init__(self):
        self.history = []

    def add(self, text):
        if text and (not self.history or text != self.history[0]):
            self.history.insert(0, text)
            self.history = self.history[:20]

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("剪贴板模拟输入工具")
        self.clipboard = QApplication.clipboard()
        self.clipboard_history = ClipboardHistory()
        self.hotkey_manager = HotkeyManager()
        self.typing_thread = None

        self.config_file = "config.json"
        self.load_config()

        self.init_ui()
        self.update_clipboard_history()

        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.update_hotkey()

    def load_config(self):
        self.config = {
            "hotkey": "control + alt + v",
            "type_interval": 5,
            "auto_add_to_table": True
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except:
                pass

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f)
        except:
            QMessageBox.warning(self, "警告", "保存配置失败")

    def init_ui(self):
        layout = QVBoxLayout()

        hotkey_layout = QHBoxLayout()
        self.hotkey_label = QLabel("全局快捷键：")
        self.hotkey_input = HotKeyInput()
        self.hotkey_input.setText(self.config["hotkey"])
        self.hotkey_save_btn = QPushButton("保存快捷键")
        self.hotkey_save_btn.clicked.connect(self.save_hotkey)

        hotkey_layout.addWidget(self.hotkey_label)
        hotkey_layout.addWidget(self.hotkey_input)
        hotkey_layout.addWidget(self.hotkey_save_btn)
        layout.addLayout(hotkey_layout)

        self.source_label = QLabel("选择文本来源：")
        self.source_combo = QComboBox()
        self.source_combo.addItems(["剪贴板", "文本框"])
        self.source_combo.currentIndexChanged.connect(self.on_source_change)

        source_layout = QHBoxLayout()
        source_layout.addWidget(self.source_label)
        source_layout.addWidget(self.source_combo)
        layout.addLayout(source_layout)

        # 修改表格的设置
        self.history_label = QLabel("历史剪贴板内容：")
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(3)
        self.history_table.setHorizontalHeaderLabels(["日期", "内容", "操作"])
        self.history_table.setRowCount(0)

        # 设置表格的显示属性
        # self.history_table.setFixedHeight(120)  # 设置固定高度，大约显示3行
        self.history_table.horizontalHeader().setStretchLastSection(False)  # 最后一列不自动拉伸
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # 日期列自适应内容
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)  # 内容列自动拉伸
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)  # 操作列固定宽度
        self.history_table.setColumnWidth(2, 60)  # 设置操作列的宽度

        # 设置文本自动换行
        self.history_table.setWordWrap(True)
        self.history_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        layout.addWidget(self.history_label)
        layout.addWidget(self.history_table)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在这里输入文本...")
        layout.addWidget(self.text_edit)

        self.speed_label = QLabel("设置打字间隔（毫秒）：")
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(0, 10000)
        self.speed_spin.setValue(self.config["type_interval"])
        self.speed_spin.valueChanged.connect(self.on_speed_change)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.speed_spin)
        layout.addLayout(speed_layout)

        self.auto_add_checkbox = QPushButton("自动添加新剪贴板内容")
        self.auto_add_checkbox.setCheckable(True)
        self.auto_add_checkbox.setChecked(self.config["auto_add_to_table"])
        self.auto_add_checkbox.clicked.connect(self.toggle_auto_add)
        layout.addWidget(self.auto_add_checkbox)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索剪贴板内容...")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.search_history)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        button_layout = QHBoxLayout()
        self.stop_button = QPushButton("停止输入")
        self.stop_button.clicked.connect(self.stop_typing)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        self.tutorial_button = QPushButton("使用教程")
        self.tutorial_button.clicked.connect(self.show_tutorial)
        button_layout.addWidget(self.tutorial_button)

        layout.addLayout(button_layout)

        # Adding author label with artistic effect
        self.author_label = QLabel("Author: whx1216")
        self.author_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)  # Align to bottom right
        self.author_label.setStyleSheet("font-size: 9px; font-weight: bold; color: darkblue;")  # Artistic effect
        layout.addWidget(self.author_label, alignment=Qt.AlignRight | Qt.AlignBottom)

        self.setLayout(layout)
        self.on_source_change()

    def save_hotkey(self):
        new_hotkey = self.hotkey_input.get_key_sequence()
        if new_hotkey:
            formatted_hotkey = new_hotkey.lower().replace('+', ' + ')
            self.config["hotkey"] = formatted_hotkey
            self.save_config()
            self.update_hotkey()
            QMessageBox.information(self, "成功", "快捷键已更新")
        else:
            QMessageBox.warning(self, "警告", "请先设置快捷键")

    def update_hotkey(self):
        stop_checking_hotkeys()
        self.hotkey_manager.set_hotkey(self.config["hotkey"], self.start_typing)
        self.hotkey_manager.register_global_hotkey()

    def on_speed_change(self, value):
        self.config["type_interval"] = value
        self.save_config()

    def on_source_change(self):
        source = self.source_combo.currentText()
        if source == "剪贴板":
            self.history_label.show()
            self.history_table.show()
            self.text_edit.hide()
            self.select_latest_clipboard()
        else:
            self.history_label.hide()
            self.history_table.hide()
            self.text_edit.show()

    def select_latest_clipboard(self):
        if self.history_table.rowCount() > 0:
            self.history_table.selectRow(0)

    def on_clipboard_change(self):
        text = self.clipboard.text()
        if self.config["auto_add_to_table"]:
            self.add_to_history_table(text)
        self.update_clipboard_history()
        self.select_latest_clipboard()

    def update_clipboard_history(self):
        self.history_table.setRowCount(len(self.clipboard_history.history))
        for row, text in enumerate(self.clipboard_history.history):
            # 设置日期项
            date_item = QTableWidgetItem(time.strftime("%Y-%m-%d %H:%M:%S"))
            # date_item.setTextAlignment(Qt.AlignCenter)  # 日期居中对齐

            # 设置文本项
            text_item = QTableWidgetItem(text)
            text_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 文本左对齐

            # 创建删除按钮
            delete_button = QPushButton("删除")
            delete_button.setFixedWidth(50)  # 设置按钮宽度
            delete_button.clicked.connect(lambda checked, row=row: self.confirm_delete(row))

            self.history_table.setItem(row, 0, date_item)
            self.history_table.setItem(row, 1, text_item)
            self.history_table.setCellWidget(row, 2, delete_button)

    def add_to_history_table(self, text):
        self.clipboard_history.add(text)
        self.update_clipboard_history()

    def start_typing(self):
        source = self.source_combo.currentText()
        if source == "剪贴板":
            text = self.history_table.item(self.history_table.currentRow(), 1).text() if self.history_table.currentRow() >= 0 else ""
        else:
            text = self.text_edit.toPlainText()

        if not text:
            QMessageBox.warning(self, "警告", "请输入文本内容。")
            return

        interval = self.speed_spin.value() / 1000

        self.stop_button.setEnabled(True)
        self.typing_thread = TypingThread(text, interval)
        self.typing_thread.progress.connect(self.update_progress)
        self.typing_thread.finished.connect(self.on_typing_finished)
        self.typing_thread.start()

    def stop_typing(self):
        if self.typing_thread and self.typing_thread.isRunning():
            self.typing_thread.stop()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_typing_finished(self):
        self.stop_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.typing_thread = None

    def toggle_auto_add(self):
        self.config["auto_add_to_table"] = self.auto_add_checkbox.isChecked()
        self.save_config()

    def search_history(self):
        search_text = self.search_input.text()
        pattern = re.compile(search_text, re.IGNORECASE)
        for row in range(self.history_table.rowCount()):
            item = self.history_table.item(row, 1)
            if item and pattern.search(item.text()):
                self.history_table.showRow(row)
            else:
                self.history_table.hideRow(row)

    def confirm_delete(self, row):
        reply = QMessageBox.question(self, '确认删除', '您确定要删除该条记录吗？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.clipboard_history.history.pop(row)
            self.update_clipboard_history()

    def show_tutorial(self):
        tutorial_message = (
            "使用教程：\n"
            "1. 选择文本来源：剪贴板或文本框\n"
            "2. 剪贴板模式下用表格选择要粘贴的内容（默认选最新复制的）\n"
            "3. 默认按ctrl+alt+v开始粘贴，可改\n"
            "如果出现异常，点击“停止输入”按钮停止模拟输入\n"
        )
        QMessageBox.information(self, "使用教程", tutorial_message)

    def closeEvent(self, event):
        stop_checking_hotkeys()
        if self.typing_thread and self.typing_thread.isRunning():
            self.typing_thread.stop()
            self.typing_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
