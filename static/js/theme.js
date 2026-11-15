/**
 * 保存されたテーマを、ページを描く前に適用する。
 *
 * baseof.html の <head> で、defer も async も付けずに読み込む。
 * <body> を描く前に <html> へ dark クラスを付け、ダークモードのときに
 * 一瞬ライトモードで描かれる（ちらつく）のを防ぐためである。
 * ボタンのアイコンの切り替えと、クリック時の処理は main.js にある。
 */
(function () {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.classList.toggle('dark', theme === 'dark');
})();
