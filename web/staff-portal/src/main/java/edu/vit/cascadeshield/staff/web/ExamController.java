package edu.vit.cascadeshield.staff.web;

import java.security.Principal;
import java.time.ZoneId;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import edu.vit.cascadeshield.staff.repo.CourseRepository;
import edu.vit.cascadeshield.staff.repo.ExamRepository;
import edu.vit.cascadeshield.staff.service.ExamService;

@Controller
public class ExamController {
    private final ExamService service;
    private final ExamRepository exams;
    private final CourseRepository courses;

    public ExamController(ExamService service, ExamRepository exams, CourseRepository courses) {
        this.service = service;
        this.exams = exams;
        this.courses = courses;
    }

    @GetMapping("/exams")
    public String list(Model model) {
        model.addAttribute("exams", service.upcoming());
        return "exams/list";
    }

    @GetMapping("/exams/new")
    public String newForm(Model model) {
        model.addAttribute("examForm", new ExamForm());
        model.addAttribute("courses", courses.findAll());
        return "exams/new";
    }

    @PostMapping("/exams")
    public String create(@ModelAttribute ExamForm form, BindingResult binding, Principal user, Model model,
            RedirectAttributes flash) {
        if (binding.hasErrors()) {
            model.addAttribute("courses", courses.findAll());
            return "exams/new";
        }
        // datetime-local has no offset: the instructor means the server's own time zone
        var start = form.getStartAt() == null ? null : form.getStartAt().atZone(ZoneId.systemDefault()).toOffsetDateTime();
        var input = new ExamService.ExamInput(form.getCourse(), start, form.getDurationMin(), form.getExpectedStudents(), form.getTopics());
        var result = service.create(input, user.getName());
        if (!result.errors().isEmpty()) {
            result.errors().forEach((field, message) -> binding.rejectValue(field, "invalid", message));
            model.addAttribute("courses", courses.findAll());
            return "exams/new";
        }
        flash.addFlashAttribute(result.coreNotified() ? "message" : "warning",
                result.coreNotified() ? "Exam saved and CascadeShield notified." : "Saved, but CascadeShield was not notified");
        return "redirect:/exams";
    }

    @PostMapping("/exams/{id}/delete")
    public String delete(@PathVariable long id, RedirectAttributes flash) {
        exams.deleteById(id);
        flash.addFlashAttribute("message", "Exam deleted.");
        return "redirect:/exams";
    }
}
