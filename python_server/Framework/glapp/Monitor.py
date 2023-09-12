import glfw
import glfw.GLFW as GLFW_CONSTANTS

class Monitor:

    def __init__(self, monitor):
        self.internal_monitor = monitor
        self.internal_name = glfw.get_monitor_name(monitor).decode('utf-8')
        self.position = glfw.get_monitor_pos(monitor)
        self.size = glfw.get_monitor_physical_size(monitor)
        print(f" -> {self.internal_name} sixe:({self.size[0]}x{self.size[1]}) at position ({self.position[0]}, {self.position[1]})")
        self.modes = glfw.get_video_modes(self.internal_monitor)
        self.max_resolution = (0, 0)
        self.max_resolution_refresh_rate = 0.0
        self.max_resolution_mode_index = -1
        self.max_pixels = 0
        self.max_pixels_resolution = (0, 0)
        self.max_pixels_refresh_rate = 0.0
        self.max_pixels_mode_index = -1
        i = 0
        for mode in self.modes:
            if (mode.size.width >= self.max_resolution[0] and mode.size.height >= self.max_resolution[1]) or mode.refresh_rate >= self.max_resolution_refresh_rate:
                self.max_resolution = (mode.size.width, mode.size.height)
                self.max_resolution_refresh_rate = mode.refresh_rate
                self.max_resolution_mode_index = i
            if (mode.size.width * mode.size.height > self.max_pixels) or mode.refresh_rate >= self.max_pixels_refresh_rate:
                self.max_pixels = mode.size.width * mode.size.height
                self.max_pixels_resolution = (mode.size.width, mode.size.height)
                self.max_pixels_refresh_rate = mode.refresh_rate
                self.max_pixels_mode_index = i
            i += 1
        print("    max resolution (width, height) is (%d. %d) at %.2fHz" % 
              (self.max_resolution[0], self.max_resolution[1], self.max_resolution_refresh_rate))
        if self.max_pixels_mode_index != self.max_resolution_mode_index:
            print("    max pixels (width*height) is (%d. %d) at %fHz is different!" % (self.max_pixels_resolution[0], self.max_pixels_resolution[1], self.max_pixels_refresh_rate))

    def get_max_resolution(self):
        return self.max_resolution, self.max_resolution_refresh_rate
