// モーダル（表示フィルタ・並び替え・情報元）の開閉。
// 開くボタンには data-modal-open="モーダルのid"、閉じるボタンには data-modal-close を付ける。
// モーダルは #modal-backdrop の直下に置く。モーダルを追加しても、このファイルを変更する必要はない。
const Modal = {
    backdrop: document.getElementById('modal-backdrop'),

    open(id) {
        const modal = document.getElementById(id);
        if (!this.backdrop || !modal) return;
        this.backdrop.classList.remove('hidden');
        this.backdrop.classList.add('flex');
        modal.classList.remove('hidden');
    },

    close() {
        if (!this.backdrop) return;
        this.backdrop.classList.add('hidden');
        this.backdrop.classList.remove('flex');
        Array.from(this.backdrop.children).forEach(modal => modal.classList.add('hidden'));
    },
};

document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-modal-open]');
    if (opener) {
        Modal.open(opener.dataset.modalOpen);
        return;
    }
    // 閉じるボタンか、モーダルの外側（背景）をクリックしたときに閉じる
    if (e.target.closest('[data-modal-close]') || e.target === Modal.backdrop) {
        Modal.close();
    }
});
