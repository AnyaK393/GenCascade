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
  <title>CascadeShield system status</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; line-height: 1.5; background: #f8fafc; color: #1e293b; }
    body.dark { background: #0f172a; color: #e2e8f0; }
    main { max-width: 52rem; margin: 0 auto; padding: 1rem; }
    a { color: inherit; }
    .card { padding: 1.5rem; border-radius: .75rem; color: #fff; margin-bottom: 1rem; }
    .card.green { background: #15803d; } .card.amber { background: #b45309; }
    .card.blue { background: #1d4ed8; } .card.red { background: #b91c1c; } .card.none { background: #475569; }
    .card h2 { margin: 0 0 .25rem; font-size: 1.5rem; }
    .badges { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
    .badge { padding: .2rem .7rem; border-radius: 999px; background: #e2e8f0; color: #1e293b; font-size: .875rem; font-weight: 600; }
    .badge.on { background: #bbf7d0; color: #14532d; } .badge.off { background: #fecaca; color: #7f1d1d; }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: .4rem .6rem; border-bottom: 1px solid #94a3b8; text-align: left; }
    footer { margin-top: 1rem; font-size: .875rem; }
  </style>
</head>
<body class="<c:out value='${theme}'/>">
<main>
  <h1>CascadeShield system status</h1>

  <c:choose>
    <c:when test="${empty status}">
      <div class="card none"><h2>Checking…</h2><p>The first status check has not finished yet.</p></div>
    </c:when>
    <c:otherwise>
      <div class="card <c:out value='${status.color}'/>">
        <h2><c:out value="${status.levelName}"/></h2>
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
