import sys
import os
import json
import re
import requests
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QTextEdit, QFileDialog, QMessageBox, QProgressBar
)
from PyQt6.QtCore import QThread, pyqtSignal

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("save_dir", os.getcwd())
        except Exception:
            pass
    return os.getcwd()

def save_config(save_dir):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"save_dir": save_dir}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def normalize_doc_num(doc_num):
    doc_num = doc_num.strip().upper()
    pct_match = re.match(r'^PCT/([A-Z]{2})(\d{4})/(\d+)$', doc_num)
    if pct_match:
        country, year, seq = pct_match.groups()
        return f"PCT/{country}{year}/{seq.zfill(6)}"
    return doc_num

class WipoScraperThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, doc_num, save_path):
        super().__init__()
        self.doc_num = doc_num
        self.save_path = save_path

    def run(self):
        try:
            self.progress_signal.emit("WIPO 서버 접속 준비 중...")
            search_term = normalize_doc_num(self.doc_num)
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            url = f"https://patentscope.wipo.int/search/en/detail.jsf?docId={search_term}&tab=FULLTEXT"
            
            self.progress_signal.emit(f"WIPO 공보 데이터 요청 중... ({search_term})")
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                self.finished_signal.emit(False, f"서버 응답 오류 (상태 코드: {response.status_code})")
                return

            self.progress_signal.emit("TXT 탭 본문 텍스트 파싱 중...")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            content = soup.find(id="detailMainForm:tabs") or soup.find(class_="ps-tab-content")
            
            if content:
                text_data = content.get_text(separator="\n", strip=True)
            else:
                text_data = soup.get_text(separator="\n", strip=True)

            if not text_data.strip():
                self.finished_signal.emit(False, "텍스트를 추출하지 못했습니다. 공개번호를 다시 확인해 주세요.")
                return

            with open(self.save_path, "w", encoding="utf-8") as f:
                f.write(text_data)

            self.finished_signal.emit(True, f"성공적으로 저장되었습니다:\n{self.save_path}")

        except Exception as e:
            self.finished_signal.emit(False, f"오류 발생: {str(e)}")

class WipoApp(QWidget):
    def __init__(self):
        super().__init__()
        self.save_dir = load_config()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("WIPO 특허 공보 TXT 자동 다운로더")
        self.resize(550, 350)

        layout = QVBoxLayout()

        input_layout = QHBoxLayout()
        input_label = QLabel("국제공개번호:")
        self.doc_input = QLineEdit()
        self.doc_input.setPlaceholderText("예: WO2026123456A1 또는 PCT/US2025/012345")
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.doc_input)
        layout.addLayout(input_layout)

        folder_layout = QHBoxLayout()
        folder_label = QLabel("저장 폴더:")
        self.folder_path_label = QLineEdit(self.save_dir)
        self.folder_path_label.setReadOnly(True)
        btn_select_folder = QPushButton("폴더 변경")
        btn_select_folder.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_path_label)
        folder_layout.addWidget(btn_select_folder)
        layout.addLayout(folder_layout)

        self.btn_start = QPushButton("TXT 생성")
        self.btn_start.setStyleSheet("font-weight: bold; padding: 8px; font-size: 14px;")
        self.btn_start.clicked.connect(self.start_download)
        layout.addWidget(self.btn_start)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        self.setLayout(layout)

    def select_folder(self):
        selected_dir = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.save_dir)
        if selected_dir:
            self.save_dir = selected_dir
            self.folder_path_label.setText(self.save_dir)
            save_config(self.save_dir)
            self.log_area.append(f"저장 폴더가 변경되었습니다: {self.save_dir}")

    def start_download(self):
        doc_num = self.doc_input.text().strip()
        if not doc_num:
            QMessageBox.warning(self, "경고", "국제공개번호를 입력해 주세요.")
            return

        safe_filename = re.sub(r'[\\/*?:"<>|]', '_', doc_num) + ".txt"
        file_path = os.path.join(self.save_dir, safe_filename)

        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self, '덮어쓰기 확인', 
                f"이미 동일한 파일이 존재합니다.\n덮어쓰시겠습니까?\n\n{safe_filename}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.log_area.append("작업이 취소되었습니다.")
                return

        self.btn_start.setEnabled(False)
        self.progress_bar.show()
        self.log_area.append(f"--- 작업 시작: {doc_num} ---")

        self.thread = WipoScraperThread(doc_num, file_path)
        self.thread.progress_signal.connect(self.update_log)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def update_log(self, message):
        self.log_area.append(message)

    def on_finished(self, success, message):
        self.progress_bar.hide()
        self.btn_start.setEnabled(True)
        self.log_area.append(message)
        
        if success:
            QMessageBox.information(self, "완료", message)
        else:
            QMessageBox.critical(self, "오류", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = WipoApp()
    ex.show()
    sys.exit(app.exec())
