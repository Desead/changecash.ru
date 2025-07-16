import { selectCoin } from "./dropdown.js";

export function initSwapButton() {
    const swapButton = document.getElementById("swap-button");
    const swapIcon = swapButton?.querySelector("i");

    const leftInput = document.getElementById("leftMoneyInput");
    const rightInput = document.getElementById("rightMoneyInput");
    const leftAmount = document.getElementById("id_left_amount");
    const rightAmount = document.getElementById("id_right_amount");

    swapButton?.addEventListener("click", () => {
        swapIcon?.classList.add("swap-rotated");
        setTimeout(() => swapIcon?.classList.remove("swap-rotated"), 400);

        const leftVal = leftInput.value;
        const rightVal = rightInput.value;

        const amount = rightAmount.value;
        if (amount && !isNaN(parseFloat(amount))) {
            leftAmount.value = parseFloat(amount);
        }

        selectCoin("left", rightVal);
        selectCoin("right", leftVal);
    });
}
