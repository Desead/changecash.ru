import { selectCoin } from "./dropdown.js";
import { createDropdownItem, createSearchInput } from "./dropdown.js";

const leftInput = document.getElementById("leftMoneyInput");
const rightInput = document.getElementById("rightMoneyInput");

const leftDropdown = document.getElementById("leftMoneyOptions");
const rightDropdown = document.getElementById("rightMoneyOptions");

const defaultLeft = "BTC Bitcoin";
const defaultRight = "USDT TRC20";

export function initCoinSelectors() {
    fetch("/api/coins/")
        .then(res => res.json())
        .then(data => {
            const coins = data.coins || [];
            const leftList = coins.filter(c => !!c.deposit && !!c.adeposit);
            const rightList = coins.filter(c => !!c.withdraw && !!c.awithdraw);

            leftDropdown.innerHTML = "";
            rightDropdown.innerHTML = "";

            leftDropdown.appendChild(createSearchInput("leftMoneyOptions", leftList));
            rightDropdown.appendChild(createSearchInput("rightMoneyOptions", rightList));

            leftList.forEach(c => leftDropdown.appendChild(createDropdownItem(c)));
            rightList.forEach(c => rightDropdown.appendChild(createDropdownItem(c)));

            selectCoin("left", defaultLeft);
            selectCoin("right", defaultRight);
        })
        .catch(err => console.error("Ошибка загрузки монет:", err));
}
