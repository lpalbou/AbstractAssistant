"""
Web server for AbstractAssistant's modern HTML/CSS interface.

Serves the web interface and handles WebSocket communication between
the frontend and the Python backend.
"""

import asyncio
import json
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("Warning: websockets not available. Install with: pip install websockets")

try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import Request, Response, WebSocketResponse
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("Warning: aiohttp not available. Install with: pip install aiohttp")

from .core.llm_manager import LLMManager


class WebServer:
    """Web server for the AbstractAssistant interface."""
    
    def __init__(self, llm_manager: LLMManager, config=None, debug: bool = False):
        """Initialize the web server.
        
        Args:
            llm_manager: LLM manager instance
            config: Configuration object
            debug: Enable debug mode
        """
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        
        # Server state
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.websocket_clients: set = set()
        
        # Configuration
        self.host = "localhost"
        self.port = 8080
        self.websocket_port = 8765
        
        # Paths
        self.web_dir = Path(__file__).parent.parent / "web"
        
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logging.getLogger(__name__)
    
    async def create_app(self) -> web.Application:
        """Create the aiohttp application."""
        app = web.Application()
        
        # Add routes
        app.router.add_get('/', self.serve_index)
        app.router.add_get('/ws', self.websocket_handler)
        app.router.add_static('/', self.web_dir, name='static')
        
        return app
    
    async def serve_index(self, request: Request) -> Response:
        """Serve the main index.html file."""
        index_file = self.web_dir / "index.html"
        
        if not index_file.exists():
            return web.Response(text="Index file not found", status=404)
        
        with open(index_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return web.Response(text=content, content_type='text/html')
    
    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_clients.add(ws)
        self.logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self.handle_websocket_message(ws, data)
                    except json.JSONDecodeError as e:
                        await self.send_error(ws, f"Invalid JSON: {e}")
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
        finally:
            self.websocket_clients.discard(ws)
            self.logger.info(f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}")
        
        return ws
    
    async def handle_websocket_message(self, ws: WebSocketResponse, data: Dict[str, Any]):
        """Handle incoming WebSocket messages."""
        message_type = data.get('type')
        
        if message_type == 'message':
            await self.handle_chat_message(ws, data)
        elif message_type == 'get_status':
            await self.send_status(ws)
        elif message_type == 'get_providers':
            await self.send_providers(ws)
        else:
            await self.send_error(ws, f"Unknown message type: {message_type}")
    
    async def handle_chat_message(self, ws: WebSocketResponse, data: Dict[str, Any]):
        """Handle chat messages from the frontend."""
        try:
            message = data.get('content', '')
            provider = data.get('provider', self.llm_manager.current_provider)
            model = data.get('model', self.llm_manager.current_model)
            
            if not message:
                await self.send_error(ws, "Empty message")
                return
            
            # Update status
            await self.send_status_update("generating", "Generating response...")
            
            # Generate response in a separate thread to avoid blocking
            def generate_response():
                try:
                    response = self.llm_manager.generate_response(
                        message=message,
                        provider=provider,
                        model=model
                    )
                    return response
                except Exception as e:
                    return f"Error: {str(e)}"
            
            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, generate_response)
            
            # Send response
            await self.send_response(ws, response)
            await self.send_status_update("ready", "Ready")
            
        except Exception as e:
            self.logger.error(f"Error handling chat message: {e}")
            await self.send_error(ws, f"Error processing message: {str(e)}")
            await self.send_status_update("ready", "Ready")
    
    async def send_response(self, ws: WebSocketResponse, content: str):
        """Send a chat response to the frontend."""
        token_usage = self.llm_manager.get_token_usage()
        
        message = {
            'type': 'response',
            'content': content,
            'tokens': token_usage.current_session,
            'timestamp': time.time()
        }
        
        await ws.send_str(json.dumps(message))
    
    async def send_error(self, ws: WebSocketResponse, error_message: str):
        """Send an error message to the frontend."""
        message = {
            'type': 'error',
            'message': error_message,
            'timestamp': time.time()
        }
        
        await ws.send_str(json.dumps(message))
    
    async def send_status(self, ws: WebSocketResponse):
        """Send current status to the frontend."""
        status_info = self.llm_manager.get_status_info()
        
        message = {
            'type': 'status',
            'status': 'ready',
            'provider': status_info['provider'],
            'model': status_info['model'],
            'tokens_current': status_info['tokens_current'],
            'tokens_max': status_info['tokens_max'],
            'timestamp': time.time()
        }
        
        await ws.send_str(json.dumps(message))
    
    async def send_status_update(self, status: str, message: str):
        """Broadcast status update to all connected clients."""
        update = {
            'type': 'status',
            'status': status,
            'message': message,
            'timestamp': time.time()
        }
        
        # Send to all connected clients
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_str(json.dumps(update))
            except Exception:
                disconnected.add(ws)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected
    
    async def send_providers(self, ws: WebSocketResponse):
        """Send available providers to the frontend."""
        providers = self.llm_manager.get_providers()
        
        provider_data = {}
        for key, info in providers.items():
            provider_data[key] = {
                'name': info.display_name,
                'models': info.models,
                'default_model': info.default_model
            }
        
        message = {
            'type': 'providers',
            'providers': provider_data,
            'timestamp': time.time()
        }
        
        await ws.send_str(json.dumps(message))
    
    async def start_server(self):
        """Start the web server."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp is required for the web server. Install with: pip install aiohttp")
        
        try:
            self.app = await self.create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            url = f"http://{self.host}:{self.port}"
            self.logger.info(f"Web server started at {url}")
            
            if self.debug:
                print(f"🌐 AbstractAssistant web interface available at: {url}")
                print(f"🔌 WebSocket server running on port: {self.websocket_port}")
            
            return url
            
        except Exception as e:
            self.logger.error(f"Failed to start web server: {e}")
            raise
    
    async def stop_server(self):
        """Stop the web server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        # Close all WebSocket connections
        for ws in list(self.websocket_clients):
            await ws.close()
        self.websocket_clients.clear()
        
        self.logger.info("Web server stopped")
    
    def run_server(self):
        """Run the server in the current thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.start_server())
            loop.run_forever()
        except KeyboardInterrupt:
            self.logger.info("Server interrupted by user")
        finally:
            loop.run_until_complete(self.stop_server())
            loop.close()
    
    def start_in_thread(self) -> str:
        """Start the server in a background thread."""
        def run():
            self.run_server()
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        
        # Wait a moment for server to start
        time.sleep(1)
        
        url = f"http://{self.host}:{self.port}"
        return url
    
    def open_browser(self, url: str):
        """Open the web interface in the default browser."""
        try:
            webbrowser.open(url)
            if self.debug:
                print(f"🚀 Opened {url} in your default browser")
        except Exception as e:
            self.logger.error(f"Failed to open browser: {e}")
            if self.debug:
                print(f"Please manually open: {url}")


class SimpleWebServer:
    """Fallback simple web server if aiohttp is not available."""
    
    def __init__(self, llm_manager: LLMManager, config=None, debug: bool = False):
        """Initialize the simple web server."""
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        self.web_dir = Path(__file__).parent.parent / "web"
        
    def start_simple_server(self) -> str:
        """Start a simple HTTP server for static files."""
        import http.server
        import socketserver
        import os
        
        port = 8080
        
        # Change to web directory
        os.chdir(self.web_dir)
        
        handler = http.server.SimpleHTTPRequestHandler
        
        def run_server():
            with socketserver.TCPServer(("", port), handler) as httpd:
                if self.debug:
                    print(f"🌐 Simple web server started at http://localhost:{port}")
                    print("⚠️  Note: This is a static-only server. WebSocket features won't work.")
                    print("   Install aiohttp for full functionality: pip install aiohttp")
                httpd.serve_forever()
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        
        url = f"http://localhost:{port}"
        return url
