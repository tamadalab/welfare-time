/**
 * Sort Management Module
 */

const Sort = {
    current: 'status',
    // カテゴリ順で並べるときの順序。表示フィルタのカテゴリの一覧と同じ順にする
    categoryOrder: [],

    /**
     * Load sort preference from localStorage
     */
    load() {
        this.current = localStorage.getItem('ksu-harapeco-sort') || 'status';
    },

    /**
     * Save sort preference to localStorage
     */
    save() {
        localStorage.setItem('ksu-harapeco-sort', this.current);
    },

    /**
     * Initialize sort UI
     * @param {Function} onUpdate - Callback when sort changes
     * @param {Array<string>} categories - Category names in display order
     */
    initUI(onUpdate, categories = []) {
        this.categoryOrder = categories;
        document.querySelectorAll('.sort-radio').forEach(radio => {
            if (radio.value === this.current) radio.checked = true;
            radio.addEventListener('change', (e) => {
                this.current = e.target.value;
                this.save();
                onUpdate();
            });
        });
    },

    /**
     * Sort an array of shops
     * @param {Array} shops 
     * @param {Function} getStatusLabel - Function to get status label for a shop
     * @param {string} openLabel - Constant for 'Open' label
     * @returns {Array} Sorted shops
     */
    sort(shops, getStatusLabel, openLabel) {
        return [...shops].sort((a, b) => {
            if (this.current === 'status') {
                const aOpen = getStatusLabel(a) === openLabel;
                const bOpen = getStatusLabel(b) === openLabel;
                if (aOpen !== bOpen) return aOpen ? -1 : 1;
                return a.name.localeCompare(b.name, 'ja');
            } else if (this.current === 'name') {
                return a.name.localeCompare(b.name, 'ja');
            } else if (this.current === 'location') {
                return a.location.localeCompare(b.location, 'ja') || a.name.localeCompare(b.name, 'ja');
            } else if (this.current === 'category') {
                return this.categoryRank(a) - this.categoryRank(b) || a.name.localeCompare(b.name, 'ja');
            }
            return 0;
        });
    },

    /**
     * Position of the shop's category in categoryOrder. Unknown categories go last.
     * @param {Object} shop
     * @returns {number}
     */
    categoryRank(shop) {
        const index = this.categoryOrder.indexOf(shop.category);
        return index === -1 ? this.categoryOrder.length : index;
    }
};
