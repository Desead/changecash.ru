import {fetchAndUpdateRate} from "./api.js";

const leftInput = document.getElementById("leftMoneyInput");
const rightInput = document.getElementById("rightMoneyInput");

const leftLabel = document.getElementById("leftMoneyLabel");
const rightLabel = document.getElementById("rightMoneyLabel");

const leftDropdown = document.getElementById("leftMoneyOptions");
const rightDropdown = document.getElementById("rightMoneyOptions");

export function selectCoin(side, label) {
    const input = side === "left" ? leftInput : rightInput;
    const display = side === "left" ? leftLabel : rightLabel;
    const dropdown = side === "left" ? leftDropdown : rightDropdown;

    const items = dropdown.querySelectorAll("li");
    items.forEach(li => li.classList.remove("active"));

    const match = Array.from(items).find(li => li.dataset.label === label);
    if (match) match.classList.add("active");

    input.value = label;
    display.textContent = label;

    fetchAndUpdateRate();
}

export function createDropdownItem(coin, query = "") {
    const label = `${coin.name_short} ${coin.chain_long}`;
    const labelLower = label.toLowerCase();
    const queryLower = query.toLowerCase();

    const highlightedLabel = query && labelLower.includes(queryLower)
        ? label.replace(new RegExp("(" + query + ")", "ig"), "<mark>$1</mark>")
        : label;

    const iconUrl = coin.icon_src || `/static/logo_money/${coin.name_short.toUpperCase()}.png`;

    const li = document.createElement("li");
    li.dataset.label = label;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "dropdown-item d-flex align-items-center";
    button.innerHTML = `<img src="${iconUrl}" alt="${coin.name_short}" width="20" height="20" class="me-2"> ${highlightedLabel}`;

    li.appendChild(button);

    li.addEventListener("click", () => {
        selectCoin(li.parentElement.id.includes("left") ? "left" : "right", label);
    });

    return li;
}

export function createSearchInput(dropdownId, fullList) {
    const li = document.createElement("li");
    li.className = "px-3 py-2";
    li.style.position = "sticky";
    li.style.top = "0";
    li.style.background = "white";
    li.style.zIndex = "1";
    li.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.05)";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Поиск...";
    input.className = "form-control form-control-sm";

    input.addEventListener("keyup", function () {
        const query = this.value.trim().toLowerCase();
        const dropdown = document.getElementById(dropdownId);
        dropdown.querySelectorAll("li:not(:first-child)").forEach(el => el.remove());

        const filtered = fullList.filter(coin =>
            `${coin.name_short} ${coin.chain_long}`.toLowerCase().includes(query)
        );

        if (filtered.length === 0) {
            const liEmpty = document.createElement("li");
            liEmpty.innerHTML = '<span class="dropdown-item text-muted">Ничего не найдено</span>';
            dropdown.appendChild(liEmpty);
        } else {
            filtered.forEach(c => {
                const item = createDropdownItem(c, query);
                dropdown.appendChild(item);
            });
        }
    });

    li.appendChild(input);
    return li;
}
