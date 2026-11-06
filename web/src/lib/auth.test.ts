import { describe, expect, it } from "vitest";
import { authHeaders, forgetToken, saveToken, savedToken } from "./auth";

function fakeStore(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => void (data[k] = v),
    removeItem: (k: string) => void delete data[k],
    data,
  };
}

describe("the saved sign-in", () => {
  it("is kept and then forgotten", () => {
    const store = fakeStore();
    saveToken("abc", store);
    expect(store.data["marketlab-token"]).toBe("abc");
    expect(savedToken(store)).toBe("abc");
    forgetToken(store);
    expect(savedToken(store)).toBeNull();
  });

  it("still works for this page when the browser will not store anything", () => {
    const refusing = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    saveToken("kept-in-memory", refusing);
    expect(savedToken(refusing)).toBe("kept-in-memory");
    forgetToken(refusing);
    expect(savedToken(refusing)).toBeNull();
  });

  it("goes out as a bearer header, or as nothing when signed out", () => {
    expect(authHeaders("t0k3n")).toEqual({ Authorization: "Bearer t0k3n" });
    expect(authHeaders(null)).toEqual({});
  });
});
