import sys
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal


class ScriptRunner(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            text=True
        )

        for line in process.stdout:
            self.output.emit(line)

        process.wait()
        self.finished.emit()


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quotation Processing Tool")
        self.setMinimumSize(800, 500)
        self.init_ui()

    def init_ui(self):
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        self.btn_processor = QPushButton("Run Processor")
        self.btn_builder = QPushButton("Run Builder")
        self.btn_full = QPushButton("Full Execution")

        self.btn_processor.clicked.connect(
            lambda: self.run_script("python processor.py")
        )
        self.btn_builder.clicked.connect(
            lambda: self.run_script("python builder.py")
        )
        self.btn_full.clicked.connect(self.run_full)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_processor)
        btn_layout.addWidget(self.btn_builder)
        btn_layout.addWidget(self.btn_full)

        layout = QVBoxLayout()
        layout.addLayout(btn_layout)
        layout.addWidget(self.log_box)

        self.setLayout(layout)

    def run_script(self, command):
        self.log_box.append(f"\n>>> Running: {command}\n")
        self.runner = ScriptRunner(command)
        self.runner.output.connect(self.log_box.append)
        self.runner.start()

    def run_full(self):
        self.log_box.append("\n>>> Running FULL execution\n")
        self.run_script("python processor.py")
        self.runner.finished.connect(
            lambda: self.run_script("python builder.py")
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())
