import { useCallback, useEffect, useState } from "react";

type Theme = "dark" | "light";

const KEY = "arena-theme";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(KEY) as Theme | null;
    if (stored === "dark" || stored === "light") return stored;
    // 深色是主设计（霓虹 + 玻璃拟态在深色下才成立），
    // 所以首次访问默认深色，不跟随系统的浅色偏好；用户切换后会记住。
    return "dark";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
