/**
 * MindMatrix 录音模块
 */
function recorderModule() {
    return {
        isRecording: false,
        recordingTimer: '00:00',
        _mediaRecorder: null,
        _audioChunks: [],
        _recordingInterval: null,
        _recordingSeconds: 0,

        async toggleRecording() {
            if (this.isRecording) {
                this._stopRecording();
            } else {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    this._audioChunks = [];
                    this._recordingSeconds = 0;
                    this.recordingTimer = '00:00';

                    this._recordingInterval = setInterval(() => {
                        this._recordingSeconds++;
                        const m = String(Math.floor(this._recordingSeconds / 60)).padStart(2, '0');
                        const s = String(this._recordingSeconds % 60).padStart(2, '0');
                        this.recordingTimer = `${m}:${s}`;
                        if (this._recordingSeconds >= 60) this._stopRecording();
                    }, 1000);

                    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                        ? 'audio/webm;codecs=opus'
                        : 'audio/webm';

                    this._mediaRecorder = new MediaRecorder(stream, { mimeType });
                    this._mediaRecorder.ondataavailable = (e) => {
                        if (e.data.size > 0) this._audioChunks.push(e.data);
                    };

                    this._mediaRecorder.onstop = async () => {
                        stream.getTracks().forEach(t => t.stop());
                        const blob = new Blob(this._audioChunks, { type: mimeType });
                        await this._sendAudioBlob(blob);
                    };

                    this._mediaRecorder.start(250);
                    this.isRecording = true;
                    this.$nextTick(() => lucide.createIcons());
                } catch (e) {
                    alert('无法访问麦克风：' + (e.message || '请检查浏览器权限设置'));
                }
            }
        },

        _stopRecording() {
            clearInterval(this._recordingInterval);
            this._recordingInterval = null;
            this.isRecording = false;
            if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
                this._mediaRecorder.stop();
            }
            this.$nextTick(() => lucide.createIcons());
        }
    };
}
