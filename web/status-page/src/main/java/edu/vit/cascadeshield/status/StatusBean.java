package edu.vit.cascadeshield.status;

import java.io.Serializable;
import java.util.Date;

/** The current state of the system, as read by the JSP through its getters. */
public class StatusBean implements Serializable {
    private Integer level;
    private String levelName;
    private String banner;
    private String color;
    private boolean examActive;
    private String examCourse;
    private boolean coreHealthy;
    private Double risk;
    private Date checkedAt;

    public StatusBean() {
    }

    public Integer getLevel() {
        return level;
    }

    public void setLevel(Integer level) {
        this.level = level;
    }

    public String getLevelName() {
        return levelName;
    }

    public void setLevelName(String levelName) {
        this.levelName = levelName;
    }

    public String getBanner() {
        return banner;
    }

    public void setBanner(String banner) {
        this.banner = banner;
    }

    public String getColor() {
        return color;
    }

    public void setColor(String color) {
        this.color = color;
    }

    public boolean isExamActive() {
        return examActive;
    }

    public void setExamActive(boolean examActive) {
        this.examActive = examActive;
    }

    public String getExamCourse() {
        return examCourse;
    }

    public void setExamCourse(String examCourse) {
        this.examCourse = examCourse;
    }

    public boolean isCoreHealthy() {
        return coreHealthy;
    }

    public void setCoreHealthy(boolean coreHealthy) {
        this.coreHealthy = coreHealthy;
    }

    public Double getRisk() {
        return risk;
    }

    public void setRisk(Double risk) {
        this.risk = risk;
    }

    public Date getCheckedAt() {
        return checkedAt;
    }

    public void setCheckedAt(Date checkedAt) {
        this.checkedAt = checkedAt;
    }
}
