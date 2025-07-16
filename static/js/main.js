import {initCoinSelectors} from "./coins.js";
import {initSwapButton} from "./swap.js";
import {setupAmountHandlers} from "./utils.js";
import {fetchRatePeriodically} from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
    initCoinSelectors();
    initSwapButton();
    setupAmountHandlers();
    fetchRatePeriodically();
});
