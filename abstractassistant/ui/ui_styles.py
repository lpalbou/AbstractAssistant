"""
UI Styles for AbstractAssistant.

Centralized stylesheet definitions to eliminate duplication and
provide consistent styling across the application.
"""


class UIStyles:
    """Centralized UI styling constants for AbstractAssistant."""

    # Color palette
    COLORS = {
        'primary': '#007AFF',
        'secondary': '#8E8E93',
        'success': '#34C759',
        'warning': '#FF9500',
        'error': '#FF3B30',
        'background': '#F2F2F7',
        'surface': '#FFFFFF',
        'text_primary': '#000000',
        'text_secondary': '#6D6D70',
        'border': '#C6C6C8'
    }

    # Button styles
    BUTTON_STYLES = {
        'primary': f"""
            QPushButton {{
                background: {COLORS['primary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #0051D0;
            }}
            QPushButton:pressed {{
                background: #003D99;
            }}
            QPushButton:disabled {{
                background: {COLORS['secondary']};
                color: #FFFFFF80;
            }}
        """,

        'secondary': f"""
            QPushButton {{
                background: {COLORS['secondary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #6D6D70;
            }}
            QPushButton:pressed {{
                background: #48484A;
            }}
            QPushButton:disabled {{
                background: #C6C6C8;
                color: #FFFFFF80;
            }}
        """,

        'success': f"""
            QPushButton {{
                background: {COLORS['success']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #28A745;
            }}
            QPushButton:pressed {{
                background: #1E7E34;
            }}
        """,

        'warning': f"""
            QPushButton {{
                background: {COLORS['warning']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #E68900;
            }}
            QPushButton:pressed {{
                background: #CC7A00;
            }}
        """,

        'error': f"""
            QPushButton {{
                background: {COLORS['error']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #E6342A;
            }}
            QPushButton:pressed {{
                background: #CC2E24;
            }}
        """,

        'icon': """
            QPushButton {
                background: transparent;
                border: none;
                padding: 4px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 0.2);
            }
        """,

        'icon_active': f"""
            QPushButton {{
                background: {COLORS['primary']};
                color: white;
                border: none;
                padding: 4px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: #0051D0;
            }}
            QPushButton:pressed {{
                background: #003D99;
            }}
        """
    }

    # Status label styles
    STATUS_LABEL_STYLES = {
        'ready': f"""
            QLabel {{
                color: {COLORS['success']};
                font-weight: bold;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(52, 199, 89, 0.1);
                border-radius: 4px;
            }}
        """,

        'generating': f"""
            QLabel {{
                color: {COLORS['warning']};
                font-weight: bold;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(255, 149, 0, 0.1);
                border-radius: 4px;
            }}
        """,

        'error': f"""
            QLabel {{
                color: {COLORS['error']};
                font-weight: bold;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(255, 59, 48, 0.1);
                border-radius: 4px;
            }}
        """,

        'idle': f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-weight: normal;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(109, 109, 112, 0.1);
                border-radius: 4px;
            }}
        """
    }

    # ComboBox styles
    COMBO_BOX_STYLES = {
        'default': f"""
            QComboBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 12px;
                background: {COLORS['surface']};
                font-size: 13px;
                min-width: 120px;
            }}
            QComboBox:hover {{
                border-color: {COLORS['primary']};
            }}
            QComboBox:focus {{
                border-color: {COLORS['primary']};
                outline: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {COLORS['text_secondary']};
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                background: {COLORS['surface']};
                selection-background-color: {COLORS['primary']};
                selection-color: white;
                padding: 4px;
            }}
        """,

        'compact': f"""
            QComboBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 8px;
                background: {COLORS['surface']};
                font-size: 12px;
                min-width: 80px;
            }}
            QComboBox:hover {{
                border-color: {COLORS['primary']};
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
                border-radius: 6px;
                padding: 8px;
                background: {COLORS['surface']};
                font-size: 13px;
                font-family: 'Helvetica Neue', "Helvetica", Arial, sans-serif;
            }}
            QTextEdit:focus {{
                border-color: {COLORS['primary']};
                outline: none;
            }}
        """,

        'message_input': f"""
            QTextEdit {{
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
                padding: 12px 16px;
                background: {COLORS['surface']};
                font-size: 14px;
                font-family: 'Helvetica Neue', "Helvetica", Arial, sans-serif;
                max-height: 120px;
                min-height: 40px;
            }}
            QTextEdit:focus {{
                border-color: {COLORS['primary']};
                outline: none;
            }}
        """
    }

    # Panel and container styles
    PANEL_STYLES = {
        'main': f"""
            QWidget {{
                background: {COLORS['surface']};
                border-radius: 12px;
            }}
        """,

        'settings': f"""
            QWidget {{
                background: {COLORS['background']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
            }}
        """,

        'toolbar': f"""
            QWidget {{
                background: {COLORS['background']};
                border-bottom: 1px solid {COLORS['border']};
                padding: 8px 12px;
            }}
        """,

        'voice_control': f"""
            QWidget {{
                background: rgba(0, 122, 255, 0.1);
                border: 1px solid {COLORS['primary']};
                border-radius: 8px;
                padding: 8px 12px;
            }}
        """
    }

    # Voice control specific styles
    VOICE_STYLES = {
        'speaking': f"""
            QPushButton {{
                background: {COLORS['success']};
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
                background: {COLORS['warning']};
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
                background: {COLORS['secondary']};
                color: white;
                border: none;
                padding: 6px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }}
        """,

        'disabled': f"""
            QPushButton {{
                background: {COLORS['border']};
                color: {COLORS['text_secondary']};
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
                background: {COLORS['success']};
                color: white;
                border-radius: 8px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 500;
            }}
        """,

        'error': f"""
            QWidget {{
                background: {COLORS['error']};
                color: white;
                border-radius: 8px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 500;
            }}
        """,

        'info': f"""
            QWidget {{
                background: {COLORS['primary']};
                color: white;
                border-radius: 8px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: white;
                font-weight: 500;
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