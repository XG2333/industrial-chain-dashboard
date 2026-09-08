import { describe, expect, it } from "vitest";
import { simplifyIndicatorName } from "./indicatorName";

describe("simplifyIndicatorName", () => {
  it("strips frequency suffix", () => {
    expect(simplifyIndicatorName("GFEX: 碳酸锂: 主力合约: 收盘价: 日度")).toBe("碳酸锂: 主力合约");
    expect(simplifyIndicatorName("SMM: 锂辉石精矿(CIF中国) -平均价: 周度")).toBe("锂辉石精矿(CIF中国)");
  });
  it("removes indicator words and source prefix", () => {
    expect(simplifyIndicatorName("GFEX: 碳酸锂: 主力合约: 成交量: 日度")).toBe("碳酸锂: 主力合约");
    expect(simplifyIndicatorName("GFEX: 碳酸锂: 主力合约: 持仓量: 日度")).toBe("碳酸锂: 主力合约");
    expect(simplifyIndicatorName("SMM: 磷锂铝石（中国现货）（Li₂O: 6%-7%） - 平均价: 日度")).toBe(
      "磷锂铝石（中国现货）（Li₂O: 6%-7%）",
    );
  });
  it("keeps mid-title frequency words (name content)", () => {
    expect(simplifyIndicatorName("SMM: 280Ah磷酸铁锂储能电芯周度理论成本: 周度")).toBe(
      "280Ah磷酸铁锂储能电芯周度理论成本",
    );
    expect(simplifyIndicatorName("多晶硅周度产量")).toBe("多晶硅周度产量");
  });
  it("handles titles without frequency", () => {
    expect(simplifyIndicatorName("碳酸锂主力合约成交持仓比")).toBe("碳酸锂主力合约成交持仓比");
  });
});
