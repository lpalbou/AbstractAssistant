"""
UI Styles for AbstractAssistant.

Centralized stylesheet definitions to eliminate duplication and
provide consistent styling across the application.
"""


class UIStyles:
    """Centralized UI styling constants for AbstractAssistant."""

    # Color palette - Obsidian Dark with Indigo Accent
    COLORS = {
        'primary': '#6366f1',       # Indigo
        'secondary': '#4b5563',     # Cool Grey
        'success': '#10b981',       # Emerald
        'warning': '#f59e0b',       # Amber
        'error': '#ef4444',         # Rose Red
        'background': '#090d16',    # Deep Space Obsidian
        'surface': '#111827',       # Dark Charcoal Surface
        'text_primary': '#f3f4f6',  # Soft Off-white
        'text_secondary': '#9ca3af',# Cool Muted Grey
        'border': 'rgba(255, 255, 255, 0.08)' # Premium Transparent Border
    }

    # Button styles
    BUTTON_STYLES = {
        'primary': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['primary']}, stop:1 #4f46e5);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #4338ca);
            }}
            QPushButton:pressed {{
                background: #3730a3;
            }}
            QPushButton:disabled {{
                background: #1f2937;
                color: #4b5563;
                border-color: rgba(255, 255, 255, 0.03);
            }}
        """,

        'secondary': f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.05);
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.15);
            }}
            QPushButton:pressed {{
                background: rgba(255, 255, 255, 0.03);
            }}
            QPushButton:disabled {{
                background: #1f2937;
                color: #4b5563;
            }}
        """,

        'success': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['success']}, stop:1 #059669);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }}
            QPushButton:pressed {{
                background: #065f46;
            }}
        """,

        'warning': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['warning']}, stop:1 #d97706);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d97706, stop:1 #b45309);
            }}
            QPushButton:pressed {{
                background: #78350f;
            }}
        """,

        'error': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['error']}, stop:1 #dc2626);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 8px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #b91c1c);
            }}
            QPushButton:pressed {{
                background: #991b1b;
            }}
        """,

        'icon': """
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                padding: 6px;
                border-radius: 6px;
                color: #d1d5db;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.03);
            }
        """,

        'icon_active': f"""
            QPushButton {{
                background: rgba(99, 102, 241, 0.2);
                border: 1px solid rgba(99, 102, 241, 0.4);
                color: white;
                padding: 6px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.3);
            }}
            QPushButton:pressed {{
                background: rgba(99, 102, 241, 0.15);
            }}
        """
    }

    # Status label styles with radial glowing gradient effect
    STATUS_LABEL_STYLES = {
        'ready': f"""
            QLabel {{
                color: {COLORS['success']};
                font-weight: bold;
                font-size: 12px;
                padding: 6px 10px;
                background: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.25);
                border-radius: 6px;
            }}
        """,

        'generating': f"""
            QLabel {{
                color: {COLORS['warning']};
                font-weight: bold;
                font-size: 12px;
                padding: 6px 10px;
                background: rgba(245, 158, 11, 0.12);
                border: 1px solid rgba(245, 158, 11, 0.25);
                border-radius: 6px;
            }}
        """,

        'error': f"""
            QLabel {{
                color: {COLORS['error']};
                font-weight: bold;
                font-size: 12px;
                padding: 6px 10px;
                background: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
            }}
        """,

        'idle': f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-weight: normal;
                font-size: 12px;
                padding: 6px 10px;
                background: rgba(156, 163, 175, 0.12);
                border: 1px solid rgba(156, 163, 175, 0.2);
                border-radius: 6px;
            }}
        """
    }

    # ComboBox styles
    COMBO_BOX_STYLES = {
        'default': f"""
            QComboBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 6px 12px;
                background: rgba(255, 255, 255, 0.04);
                color: {COLORS['text_primary']};
                font-size: 13px;
                min-width: 120px;
            }}
            QComboBox:hover {{
                border-color: rgba(99, 102, 241, 0.3);
            }}
            QComboBox:focus {{
                border-color: {COLORS['primary']};
                outline: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {COLORS['text_secondary']};
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                background: #1e293b;
                selection-background-color: #312e81;
                selection-color: white;
                padding: 4px;
            }}
        """,

        'compact': f"""
            QComboBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 4px 8px;
                background: rgba(255, 255, 255, 0.03);
                color: {COLORS['text_primary']};
                font-size: 12px;
                min-width: 80px;
            }}
            QComboBox:hover {{
                border-color: rgba(99, 102, 241, 0.25);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 3px solid {COLORS['text_secondary']};
                margin-right: 6px;
            }}
        """
    }

    # Text input styles
    TEXT_INPUT_STYLES = {
        'default': f"""
            QTextEdit {{
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
                background: rgba(255, 255, 255, 0.03);
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto;
            }}
            QTextEdit:focus {{
                border-color: {COLORS['primary']};
                background: rgba(255, 255, 255, 0.05);
                outline: none;
            }}
        """,

        'message_input': f"""
            QTextEdit {{
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.04);
                color: {COLORS['text_primary']};
                font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto;
                max-height: 120px;
                min-height: 40px;
            }}
            QTextEdit:focus {{
                border-color: {COLORS['primary']};
                background: rgba(255, 255, 255, 0.06);
                outline: none;
            }}
        """
    }

    # Panel and container styles
    PANEL_STYLES = {
        'main': f"""
            QWidget {{
                background: {COLORS['background']};
                color: {COLORS['text_primary']};
                border-radius: 14px;
            }}
        """,

        'settings': f"""
            QWidget {{
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 12px;
            }}
        """,

        'toolbar': f"""
            QWidget {{
                background: rgba(0, 0, 0, 0.2);
                border-bottom: 1px solid {COLORS['border']};
                padding: 8px 12px;
            }}
        """,

        'voice_control': f"""
            QWidget {{
                background: rgba(99, 102, 241, 0.12);
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 10px;
                padding: 8px 12px;
            }}
        """
    }

    # Voice control specific styles
    VOICE_STYLES = {
        'speaking': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['success']}, stop:1 #059669);
                color: white;
                border: none;
                padding: 6px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }}
        """,

        'paused': f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['warning']}, stop:1 #d97706);
                color: white;
                border: none;
                padding: 6px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }}
        """,

        'idle': f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: white;
                border: 1px solid {COLORS['border']};
                padding: 6px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }}
        """,

        'disabled': f"""
            QPushButton {{
                background: #1f2937;
                color: #4b5563;
                border: none;
                padding: 6px;
                border-radius: 12px;
                font-size: 14px;
            }}
        """
    }

    # Toast notification styles
    TOAST_STYLES = {
        'success': f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['success']}, stop:1 #059669);
                color: white;
                border-radius: 10px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 600;
            }}
        """,

        'error': f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['error']}, stop:1 #dc2626);
                color: white;
                border-radius: 10px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 600;
            }}
        """,

        'info': f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLORS['primary']}, stop:1 #4f46e5);
                color: white;
                border-radius: 10px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 600;
            }}
        """
    }

    @classmethod
    def get_button_style(cls, style_type: str) -> str:
        """Get button style by type.

        Args:
            style_type: Button style type (primary, secondary, success, etc.)

        Returns:
            CSS stylesheet string
        """
        return cls.BUTTON_STYLES.get(style_type, cls.BUTTON_STYLES['primary'])

    @classmethod
    def get_status_style(cls, status: str) -> str:
        """Get status label style by status.

        Args:
            status: Status type (ready, generating, error, idle)

        Returns:
            CSS stylesheet string
        """
        return cls.STATUS_LABEL_STYLES.get(status, cls.STATUS_LABEL_STYLES['idle'])

    @classmethod
    def get_voice_style(cls, state: str) -> str:
        """Get voice control style by TTS state.

        Args:
            state: TTS state (speaking, paused, idle, disabled)

        Returns:
            CSS stylesheet string
        """
        return cls.VOICE_STYLES.get(state, cls.VOICE_STYLES['idle'])