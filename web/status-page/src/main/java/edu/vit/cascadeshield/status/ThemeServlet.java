package edu.vit.cascadeshield.status;

import java.io.IOException;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/theme")
public class ThemeServlet extends HttpServlet {
    private static final String COOKIE = "theme";
    private static final int THIRTY_DAYS_S = 30 * 24 * 3600;

    static String current(HttpServletRequest request) {
        if (request.getCookies() != null) {
            for (Cookie c : request.getCookies()) {
                if (COOKIE.equals(c.getName()) && "dark".equals(c.getValue())) {
                    return "dark";
                }
            }
        }
        return "light";
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        Cookie cookie = new Cookie(COOKIE, "dark".equals(current(request)) ? "light" : "dark");
        cookie.setMaxAge(THIRTY_DAYS_S);
        cookie.setPath(request.getContextPath() + "/");
        cookie.setHttpOnly(true);
        response.addCookie(cookie);
        response.sendRedirect(response.encodeRedirectURL(request.getContextPath() + "/"));
    }
}
