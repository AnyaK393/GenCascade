package edu.vit.cascadeshield.status;

import java.io.IOException;
import java.sql.SQLException;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

@WebServlet("/")
public class StatusServlet extends HttpServlet {
    private static final int SHOWN_ROWS = 20;
    private static final int SHARE_ROWS = 2000; // far more level changes than one day can have

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        @SuppressWarnings("unchecked")
        var latest = (AtomicReference<StatusBean>) getServletContext().getAttribute(StatusPoller.ATTRIBUTE);
        request.setAttribute("status", latest.get());

        try {
            List<HistoryRow> rows = Db.recentHistory(SHARE_ROWS);
            request.setAttribute("history", rows.subList(0, Math.min(SHOWN_ROWS, rows.size())));
            request.setAttribute("healthyShare", HistoryRow.healthyShare(rows, System.currentTimeMillis()));
        } catch (SQLException e) {
            log("history unavailable: " + e.getMessage()); // the live status must still show without MySQL
            request.setAttribute("historyError", true);
        }

        HttpSession session = request.getSession();
        Integer visits = (Integer) session.getAttribute("visits");
        session.setAttribute("visits", visits == null ? 1 : visits + 1);

        request.setAttribute("theme", ThemeServlet.current(request));
        request.getRequestDispatcher("/WEB-INF/jsp/status.jsp").forward(request, response);
    }
}
