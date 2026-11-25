// 主畫面安裝橫幅：Chromium 用 beforeinstallprompt；iOS Safari 改顯示手動步驟。
(function () {
    const root = document.getElementById('pwa-install');
    if (!root) return;

    const DISMISS_KEY = 'pwa-install-dismissed-until';
    const SNOOZE_MS = 7 * 24 * 60 * 60 * 1000;

    function storageGet(key) {
        try {
            return localStorage.getItem(key);
        } catch (err) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (err) {
            // 隱私模式可能拒絕寫入，橫幅仍可先關掉
        }
    }

    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches
            || window.matchMedia('(display-mode: fullscreen)').matches
            || window.navigator.standalone === true;
    }

    function isDismissed() {
        const until = Number(storageGet(DISMISS_KEY) || '0');
        return Number.isFinite(until) && until > Date.now();
    }

    function isIosSafari() {
        const ua = navigator.userAgent || '';
        const ios = /iphone|ipad|ipod/i.test(ua)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        return ios && /safari/i.test(ua) && !/crios|fxios|edgios|opr\//i.test(ua);
    }

    function syncLayout() {
        const version = document.querySelector('.app-version');
        const height = root.offsetHeight;
        if (version) version.style.bottom = height + 'px';
        const versionHeight = version ? version.offsetHeight : 0;
        document.body.style.paddingBottom = (height + versionHeight + 12) + 'px';
    }

    function clearLayout() {
        const version = document.querySelector('.app-version');
        if (version) version.style.bottom = '0px';
        document.body.style.paddingBottom = '';
    }

    function hide(snooze) {
        if (snooze) storageSet(DISMISS_KEY, String(Date.now() + SNOOZE_MS));
        root.hidden = true;
        clearLayout();
    }

    function show(mode) {
        root.dataset.mode = mode;
        root.hidden = false;
        syncLayout();
    }

    if (isStandalone() || isDismissed()) return;

    let deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        deferredPrompt = event;
        show('native');
    });

    window.addEventListener('appinstalled', () => {
        deferredPrompt = null;
        hide(false);
    });

    root.addEventListener('click', async (event) => {
        const action = event.target.closest('[data-action]');
        if (!action) return;
        if (action.dataset.action === 'dismiss') {
            hide(true);
            return;
        }
        if (action.dataset.action === 'install' && deferredPrompt) {
            deferredPrompt.prompt();
            const choice = await deferredPrompt.userChoice;
            deferredPrompt = null;
            hide(choice.outcome !== 'accepted');
        }
    });

    window.addEventListener('resize', () => {
        if (!root.hidden) syncLayout();
    });

    if (isIosSafari()) show('ios');
})();
