/**
 * MindMatrix 智谱矩阵 —— 前端核心逻辑
 * Powered by Alpine.js & Tailwind CSS
 */

function app() {
    return {
        // --- State ---
        isLoggedIn: false,
        showAuth: false,
        authMode: 'login', // 'login' | 'register'
        loading: false,
        sidebarOpen: false,
        currentView: 'plaza', // 'plaza' | 'chat'
        
        user: { username: '', balance: '0.00' },
        authForm: { username: '', password: '', invite_code: '' },
        
        personas: [],
        conversations: [],
        activeConvId: null,
        activeConvTitle: '新对话',
        currentPersona: { id: '', name: '', description: '' },
        
        messages: [],
        messageInput: '',
        streaming: false,

        // --- Init ---
        init() {
            this.checkAuth();
            this.fetchPersonas();
            // 每 30 秒刷新一次余额
            setInterval(() => { if(this.isLoggedIn) this.fetchMe(); }, 30000);
        },

        // --- Auth Logic ---
        async checkAuth() {
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    await this.fetchMe();
                    this.isLoggedIn = true;
                    this.loadConversations();
                } catch (e) {
                    localStorage.removeItem('token');
                }
            }
        },

        async fetchMe() {
            const res = await this.api('/api/me');
            this.user = { username: res.username, balance: res.balance.toFixed(2) };
        },

        openAuth(mode) {
            this.authMode = mode;
            this.showAuth = true;
        },

        async handleAuth() {
            this.loading = true;
            try {
                const endpoint = this.authMode === 'login' ? '/api/login' : '/api/register';
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.authForm)
                });
                const data = await res.json();
                
                if (!res.ok) throw new Error(data.detail || '认证失败');

                if (this.authMode === 'register') {
                    // 注册成功自动登录
                    this.authMode = 'login';
                    await this.handleAuth();
                    return;
                }

                localStorage.setItem('token', data.access_token);
                this.isLoggedIn = true;
                this.showAuth = false;
                await this.fetchMe();
                this.loadConversations();
                this.authForm = { username: '', password: '', invite_code: '' };
            } catch (e) {
                alert(e.message);
            } finally {
                this.loading = false;
            }
        },

        logout() {
            localStorage.removeItem('token');
            this.isLoggedIn = false;
            this.currentView = 'plaza';
            window.location.reload();
        },

        // --- Data Fetching ---
        async fetchPersonas() {
            try {
                const res = await fetch('/api/personas');
                this.personas = await res.json();
                this.$nextTick(() => lucide.createIcons());
            } catch (e) {
                console.error('获取角色失败', e);
            }
        },

        async loadConversations() {
            try {
                this.conversations = await this.api('/api/conversations');
            } catch (e) {
                console.error('获取会话失败', e);
            }
        },

        // --- Conversation Management ---
        async createNewConv(persona) {
            try {
                const res = await this.api('/api/conversations', 'POST', {
                    title: `与 ${persona.name} 的对话`,
                    persona_id: persona.id
                });
                this.conversations.unshift(res);
                this.loadConversation(res);
            } catch (e) {
                alert(e.message);
            }
        },

        async loadConversation(conv) {
            this.activeConvId = conv.id;
            this.activeConvTitle = conv.title;
            this.currentPersona = { id: conv.persona_id, name: conv.persona_name || conv.persona_id };
            this.currentView = 'chat';
            this.messages = [];
            this.sidebarOpen = false;
            
            try {
                const msgs = await this.api(`/api/conversations/${conv.id}/messages`);
                this.messages = msgs;
                this.scrollToBottom();
            } catch (e) {
                console.error('加载消息失败', e);
            }
        },

        async deleteConv(id) {
            if (!confirm('确定删除此对话吗？')) return;
            try {
                await this.api(`/api/conversations/${id}`, 'DELETE');
                this.conversations = this.conversations.filter(c => c.id !== id);
                if (this.activeConvId === id) {
                    this.currentView = 'plaza';
                    this.activeConvId = null;
                }
            } catch (e) {
                alert(e.message);
            }
        },

        // --- Chatting ---
        async sendMessage() {
            if (!this.messageInput.trim() || this.streaming) return;

            const userMsg = this.messageInput.trim();
            this.messages.push({ role: 'user', content: userMsg });
            this.messageInput = '';
            this.streaming = true;
            this.scrollToBottom();

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('token')}`
                    },
                    body: JSON.stringify({
                        conversation_id: this.activeConvId,
                        messages: this.messages
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || '发送失败');
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let aiContent = '';
                this.messages.push({ role: 'assistant', content: '' });
                const lastIdx = this.messages.length - 1;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6).trim();
                            if (dataStr === '[DONE]') {
                                this.streaming = false;
                                await this.fetchMe(); // 更新余额
                                break;
                            }
                            try {
                                const data = JSON.parse(dataStr);
                                if (data.content) {
                                    aiContent += data.content;
                                    this.messages[lastIdx].content = aiContent;
                                    this.scrollToBottom();
                                }
                                if (data.error) throw new Error(data.error);
                            } catch (e) {}
                        }
                    }
                }
            } catch (e) {
                alert(e.message);
                this.streaming = false;
            }
        },

        // --- Helpers ---
        async api(url, method = 'GET', body = null) {
            const token = localStorage.getItem('token');
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            if (token) {
                options.headers['Authorization'] = `Bearer ${token}`;
            }
            if (body) options.body = JSON.stringify(body);
            
            const res = await fetch(url, options);
            
            // 处理 401 未授权
            if (res.status === 401 && !url.includes('/login') && !url.includes('/register')) {
                localStorage.removeItem('token');
                this.isLoggedIn = false;
                return;
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '请求失败');
            return data;
        },

        renderMarkdown(text) {
            return marked.parse(text || '');
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const el = document.getElementById('message-container');
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        handleEnterKey(event) {
            if (event.key === 'Enter') {
                if (event.ctrlKey) {
                    // Ctrl + Enter: New Line
                    const cursor = event.target.selectionStart;
                    this.messageInput = this.messageInput.slice(0, cursor) + '\n' + this.messageInput.slice(cursor);
                    // Manually move cursor
                    this.$nextTick(() => {
                        event.target.selectionStart = event.target.selectionEnd = cursor + 1;
                    });
                } else {
                    // Enter: Send
                    event.preventDefault();
                    this.sendMessage();
                }
            }
        }
    };
}
