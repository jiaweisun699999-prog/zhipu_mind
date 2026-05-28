/**
 * MindMatrix 聊天与消息收发模块 (流式版：支持文字流式显示 + 条件语音播报)
 */
function chatModule() {
    return {
        messages: [],
        messageInput: '',
        streaming: false,
        voiceMode: false,

        async sendMessage() {
            if (!this.messageInput.trim() || this.streaming || !this.activeConvId) return;

            const userText = this.messageInput.trim();
            this.messageInput = '';
            this.streaming = true;

            // 1. 添加用户消息
            this.messages.push({ role: 'user', content: userText });
            this.scrollToBottom();

            // 2. 添加 AI 占位消息，并标记为新生成（用于触发音频自动播放）
            this.messages.push({ role: 'assistant', content: '', isNew: true });
            const aiIdx = this.messages.length - 1;

            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/conversations/${this.activeConvId}/chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        text: userText,
                        voice_mode: this.voiceMode
                    })
                });

                if (response.status === 402) throw new Error('余额不足');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                // 3. 处理流式响应
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith('data: ')) continue;

                        try {
                            const data = JSON.parse(trimmed.slice(6));
                            if (data.content) {
                                this.messages[aiIdx].content += data.content;
                                this.scrollToBottom();
                            } else if (data.audio_url) {
                                // 将音频 URL 赋给当前消息，触发 Alpine 渲染并渲染音频胶囊
                                this.messages[aiIdx].audio_url = data.audio_url;
                                this.scrollToBottom();
                            } else if (data.error) {
                                this.messages[aiIdx].content = `❌ 错误: ${data.error}`;
                            }
                        } catch (e) {
                            console.warn('解析流失败', e);
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
