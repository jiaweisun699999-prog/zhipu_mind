/**
 * MindMatrix 认证模块
 */
function authModule() {
    return {
        isLoggedIn: false,
        showAuth: false,
        authMode: 'login',
        loading: false,
        user: { username: '', balance: '0.00' },
        authForm: { username: '', password: '', invite_code: '' },

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
            const res = await window.apiClient.call('/api/me');
            if (res) {
                this.user = { username: res.username, balance: res.balance.toFixed(2) };
            }
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
            location.reload();
        }
    };
}
