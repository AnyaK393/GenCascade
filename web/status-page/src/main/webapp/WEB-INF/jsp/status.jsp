<%@ page contentType="text/html;charset=UTF-8" trimDirectiveWhitespaces="true" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<%@ taglib prefix="fmt" uri="jakarta.tags.fmt" %>
<%-- Without a fixed locale, fmt:formatNumber prints the raw value for clients that send no language. --%>
<fmt:setLocale value="en"/>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 40 40%27%3E%3Cpath d=%27M20 2 35 7.500v11.700c0 9.200-6.100 16.300-15 18.800C11.100 35.500 5 28.400 5 19.200V7.500z%27 fill=%27%23105e58%27/%3E%3Cpath d=%27M12 13h16v4H12z%27 fill=%27%23a7dfd6%27/%3E%3Cpath d=%27M15 19.500h10v4H15z%27 fill=%27%23f7cf6e%27/%3E%3Cpath d=%27M18 26h4v4h-4z%27 fill=%27%23e8674a%27/%3E%3C/svg%3E">
  <title>CascadeShield system status</title>
  <style>
    /* Same palette as the other sites. No entrance animation: this page reloads every 10 s. */
    @font-face { font-family: Manrope; src: url("<c:url value='/manrope.woff2'/>") format("woff2"); font-weight: 200 800; font-display: swap; }
    :root { --bg: #f6f5f0; --ink: #14242b; --soft: #566a72; --panel: #fff; --line: #e3e9eb; --head: #f2f5f6; --chip: #e3e9eb; --chip-ink: #33454e; --hover: #ecf8f6; }
    body.dark { --bg: #0d1a1f; --ink: #e3e9eb; --soft: #a3b2b8; --panel: #14242b; --line: #2b3f48; --head: #1b2e36; --chip: #2b3f48; --chip-ink: #e3e9eb; --hover: #1b2e36; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Manrope, system-ui, sans-serif; line-height: 1.6; background: var(--bg); color: var(--ink); -webkit-font-smoothing: antialiased; }
    main { max-width: 56rem; margin: 0 auto; padding: 2.5rem 1.5rem; }
    a { color: inherit; font-weight: 700; text-underline-offset: 2px; }
    header { display: flex; align-items: center; gap: .8rem; margin-bottom: 1.75rem; }
    header svg { width: 2.8rem; height: 2.8rem; flex: none; }
    h1 { margin: 0; font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.2; }
    .card { position: relative; overflow: hidden; padding: 2rem; border-radius: 1.4rem; color: #fff; margin-bottom: 1rem; box-shadow: 0 18px 36px -20px rgb(20 36 43 / .5); }
    .card::after { content: ""; position: absolute; top: -6rem; right: -4rem; width: 16rem; height: 16rem; border-radius: 50%; background: rgb(255 255 255 / .08); }
    .card.green { background: #105e58; } .card.amber { background: #8f6108; }
    .card.blue { background: #0b6087; } .card.red { background: #ab3c24; } .card.none { background: #435660; }
    .card h2 { display: flex; align-items: center; gap: .7rem; margin: 0 0 .3rem; font-size: 1.7rem; font-weight: 800; letter-spacing: -.01em; }
    .card p { margin: 0 0 .6rem; font-size: 1.05rem; }
    .card small { opacity: .85; }
    .dot { position: relative; width: .8rem; height: .8rem; flex: none; border-radius: 50%; background: #fff; }
    .dot::after { content: ""; position: absolute; inset: 0; border-radius: 50%; background: #fff; animation: beacon 1.8s cubic-bezier(0,0,.2,1) infinite; }
    @keyframes beacon { 75%, 100% { transform: scale(2.6); opacity: 0; } }
    .badges { display: flex; flex-wrap: wrap; gap: .6rem; margin-bottom: 2rem; }
    .badge { padding: .3rem .85rem; border-radius: 999px; background: var(--chip); color: var(--chip-ink); font-size: .875rem; font-weight: 700; }
    .badge.on { background: #d2efea; color: #0e4b47; } .badge.off { background: #fbdcd3; color: #8f3019; }
    main > h2 { margin: 0 0 .9rem; font-size: 1.3rem; font-weight: 800; }
    .scroll { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 1.1rem; }
    table { width: 100%; border-collapse: collapse; }
    th { color: var(--soft); font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; background: var(--head); }
    th, td { padding: .75rem 1rem; border-bottom: 1px solid var(--line); text-align: left; }
    tbody tr:last-child td { border-bottom: 0; }
    tbody tr:hover { background: var(--hover); }
    footer { margin-top: 1.5rem; color: var(--soft); font-size: .875rem; }
    @media (prefers-reduced-motion: reduce) { .dot::after { animation: none; opacity: 0; } }
  </style>
</head>
<body class="<c:out value='${theme}'/>">
<main>
  <header>
    <svg viewBox="0 0 40 40" aria-hidden="true"><path d="M20 2 35 7.500v11.700c0 9.200-6.100 16.300-15 18.800C11.100 35.500 5 28.400 5 19.200V7.500z" fill="#105e58"/><path d="M12 13h16v4H12z" fill="#a7dfd6"/><path d="M15 19.500h10v4H15z" fill="#f7cf6e"/><path d="M18 26h4v4h-4z" fill="#e8674a"/></svg>
    <h1>CascadeShield system status</h1>
  </header>

  <c:choose>
    <c:when test="${empty status}">
      <div class="card none"><h2>Checking…</h2><p>The first status check has not finished yet.</p></div>
    </c:when>
    <c:otherwise>
      <div class="card <c:out value='${status.color}'/>">
        <h2><span class="dot"></span><c:out value="${status.levelName}"/></h2>
        <p><c:out value="${status.banner}"/></p>
        <small>Checked at <fmt:formatDate value="${status.checkedAt}" pattern="HH:mm:ss"/></small>
      </div>
      <div class="badges">
        <c:if test="${status.examActive}">
          <span class="badge off">Exam in progress: <c:out value="${status.examCourse}"/></span>
        </c:if>
        <c:choose>
          <c:when test="${status.coreHealthy}"><span class="badge on">Control room: online</span></c:when>
          <c:otherwise><span class="badge off">Control room: offline</span></c:otherwise>
        </c:choose>
        <c:if test="${not empty status.risk}">
          <span class="badge">LLM risk: <fmt:formatNumber value="${status.risk}" maxFractionDigits="2"/></span>
        </c:if>
        <c:if test="${not empty healthyShare}">
          <span class="badge">Healthy, last 24 h: <fmt:formatNumber value="${healthyShare}" maxFractionDigits="1"/>%</span>
        </c:if>
      </div>
    </c:otherwise>
  </c:choose>

  <h2>Level history</h2>
  <c:choose>
    <c:when test="${historyError}"><p>History is unavailable right now.</p></c:when>
    <c:when test="${empty history}"><p>No level changes recorded yet.</p></c:when>
    <c:otherwise>
      <div class="scroll">
        <table>
          <thead><tr><th>Time</th><th>Level</th><th>Banner</th><th>Exam</th></tr></thead>
          <tbody>
            <c:forEach var="row" items="${history}">
              <tr>
                <td><fmt:formatDate value="${row.changedAt}" pattern="dd MMM HH:mm:ss"/></td>
                <td><c:out value="${empty row.level ? '-' : row.level}"/></td>
                <td><c:out value="${row.banner}"/></td>
                <td><c:out value="${row.examActive ? 'Yes' : 'No'}"/></td>
              </tr>
            </c:forEach>
          </tbody>
        </table>
      </div>
    </c:otherwise>
  </c:choose>

  <footer>
    <c:url var="themeUrl" value="/theme"/>
    <a href="<c:out value='${themeUrl}'/>">Switch theme</a> · Visits this session: <c:out value="${sessionScope.visits}"/>
  </footer>
</main>
</body>
</html>
