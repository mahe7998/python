class Geometry2D:

    def __init__(self, bounding_box):
        self.update_bouding_box(bounding_box)

    def update_bouding_box(self, bounding_box):
        self.bounding_box = bounding_box
    
    def get_bounding_box(self):
        return self.bounding_box

    def draw(self, display_width, display_height):
        pass

    def update_display_size(self, display_width, display_height):
        pass
