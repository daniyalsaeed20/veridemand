import { describe, expect, it } from "vitest";

import {
  isPersistentLivenessOutage,
  LIVENESS_OUTAGE_STREAK_THRESHOLD,
  nextLivenessFailureStreak,
} from "./useHealth";
import { ApiError } from "../../api/http";

describe("liveness failure streak", () => {
  it("does not treat a single transport failure as persistent outage", () => {
    const streak = nextLivenessFailureStreak(0, {
      success: false,
      transportFailure: true,
    });
    expect(streak).toBe(1);
    expect(
      isPersistentLivenessOutage(
        streak,
        true,
        new ApiError("timeout", { code: "liveness_timeout" }),
      ),
    ).toBe(false);
  });

  it("requires consecutive failures before persistent outage", () => {
    let streak = 0;
    streak = nextLivenessFailureStreak(streak, { success: false, transportFailure: true });
    streak = nextLivenessFailureStreak(streak, { success: false, transportFailure: true });
    expect(streak).toBe(LIVENESS_OUTAGE_STREAK_THRESHOLD);
    expect(
      isPersistentLivenessOutage(streak, true, new ApiError("down", { code: "network_error" })),
    ).toBe(true);
  });

  it("clears streak immediately after success", () => {
    const streak = nextLivenessFailureStreak(3, { success: true, transportFailure: false });
    expect(streak).toBe(0);
    expect(isPersistentLivenessOutage(streak, false, undefined)).toBe(false);
  });
});
