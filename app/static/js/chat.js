/**
 * MindMatrix 聊天与消息收发模块
 */
function chatModule() {
    return {
        messages: [],
        messageInput: '',
        streaming: false,

        async sendMessage() {
            if (!this.messageInput.trim() || this.streaming || !this.activeConvId) return;

            const userText = this.messageInput.trim();
            this.messageInput = '';
            this.streaming = true;

            // 1. 添加用户消息
            this.messages.push({ role: 'user', content: userText });
            this.scrollToBottom();

            // 2. 添加 AI 占位消息
            this.messages.push({ role: 'assistant', content: '', _loading: true });
            const aiIdx = this.messages.length - 1;

            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        conversation_id: this.activeConvId,
                        messages: this.messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }))
                    })
                });

                if (response.status === 402) throw new Error('余额不足，请充值后继续使用');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                // 3. 读取流
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                this.messages[aiIdx]._loading = false;
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // 最后一项可能是残缺的，留到下次处理
                    
                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith('data: ')) continue;
                        
                        try {
                            const data = JSON.parse(trimmed.slice(6));
                            if (data.content) {
                                this.messages[aiIdx].content += data.content;
                                this.scrollToBottom();
                            } else if (data.error) {
                                this.messages[aiIdx].content = `❌ 错误: ${data.error}`;
                            }
                        } catch (e) {
                            console.warn('解析流片段失败', e, trimmed);
                        }
                    }
                }
                await this.fetchMe();
            } catch (e) {
                this.messages[aiIdx].content = `❌ 请求失败：${e.message}`;
            } finally {
                this.streaming = false;
                this.scrollToBottom();
            }
        },

        async _sendAudioBlob(blob) {
            if (!this.activeConvId) {
                alert('请先选择一个对话角色');
                return;
            }
            this.streaming = true;
            this.messages.push({ role: 'user', content: '🎤 语音消息（转录中…）' });
            this.messages.push({ role: 'assistant', content: '', _loading: true });
            const userIdx = this.messages.length - 2;
            const aiIdx   = this.messages.length - 1;
            this.scrollToBottom();

            try {
                const formData = new FormData();
                formData.append('audio_file', blob, 'recording.webm');
                const data = await this._callChatAPI(formData);
                this.messages[userIdx] = { role: 'user', content: `🎤 ${data.user_text}` };
                this.messages[aiIdx] = { role: 'assistant', content: data.reply };
                if (data.audio_url) this._playAudio(data.audio_url);
                await this.fetchMe();
            } catch (e) {
                this.messages[aiIdx] = { role: 'assistant', content: `❌ 请求失败：${e.message}` };
            } finally {
                this.streaming = false;
                this.scrollToBottom();
            }
        },

        async _callChatAPI(formData) {
            const token = localStorage.getItem('token');
            const res = await fetch(`/api/conversations/${this.activeConvId}/chat`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });
            if (res.status === 402) throw new Error('余额不足，请充值后继续使用');
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            return await res.json();
        },

        _playAudio(url) {
            try {
                const audio = new Audio(url);
                audio.play().catch(e => console.warn('[Audio] 自动播放被阻止', e));
            } catch (e) {
                console.error('[Audio] 播放失败', e);
            }
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const el = document.getElementById('message-container');
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        renderMarkdown(text) {
            if (!text) return '';
            return marked.parse(text);
        },

        handleEnterKey(event) {
            if (event.key === 'Enter') {
                if (event.ctrlKey) {
                    const cursor = event.target.selectionStart;
                    this.messageInput = this.messageInput.slice(0, cursor) + '\n' + this.messageInput.slice(cursor);
                    this.$nextTick(() => { event.target.selectionStart = event.target.selectionEnd = cursor + 1; });
                } else {
                    event.preventDefault();
                    this.sendMessage();
                }
            }
        }
    };
}
