from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, white, HexColor

def get_row_y_coordinate(r):
    """
    Returns the Y coordinate (in PDF points) for a given row index r (0 to 24).
    Groups rows in blocks of 5 with a gap between blocks.
    """
    block_idx = r // 5
    row_in_block = r % 5
    return 590 - (block_idx * 105) - (row_in_block * 18)

def draw_omr_sheet_on_canvas(c, participant=None):
    """
    Draws the complete OMR sheet layout onto a ReportLab canvas.
    If a participant object is provided, pre-prints their details and pre-bubbles their Roll No and Group.
    """
    # 1. Header Information Table
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.5)
    
    # Outer rectangle for header info
    c.rect(70, 715, 455, 75, fill=0)
    # Inner divider lines
    c.line(70, 740, 525, 740)
    c.line(70, 765, 525, 765)
    
    # Header Labels
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(black)
    c.drawString(80, 772, "NAME :")
    c.drawString(80, 747, "EXAM :")
    c.drawString(80, 722, "DATE :")
    
    # Pre-fill participant data if provided
    if participant:
        c.setFont("Helvetica", 11)
        c.drawString(140, 772, participant.full_name.upper())
        c.drawString(140, 747, "OMR EVALUATION SHEET")
        
        # Display School and Group
        school_name = participant.school.name
        group_name = participant.get_group_display()
        c.drawString(140, 722, f"{school_name.upper()}   |   {group_name.upper()} GROUP")
        
    # Draw OMR Grid and Registration Anchors
    anchor_size = 14
    
    def draw_anchor(x, y):
        c.setFillColor(black)
        c.rect(x - anchor_size/2, y - anchor_size/2, anchor_size, anchor_size, fill=1, stroke=0)
        
    # Draw the 4 corner anchors
    draw_anchor(40, 660)  # Top-Left
    draw_anchor(555, 660) # Top-Right
    draw_anchor(40, 60)   # Bottom-Left
    draw_anchor(555, 60)  # Bottom-Right
    
    # Optional bounding box connecting the anchors
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.5)
    c.rect(40, 60, 515, 600, fill=0)
    
    bubble_r = 6.0
    
    # Left Column: Exam Set, Roll No, and Group
    col0_x = 70
    
    # 1. Exam Set (Left empty for students to bubble manually)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#0D2B4E"))
    c.drawString(col0_x, 635, "Exam Set")
    
    c.setFont("Helvetica", 8)
    c.drawString(col0_x, 622, "A")
    c.drawString(col0_x + 22, 622, "B")
    
    for idx in range(2):
        bx = col0_x + 3 + (idx * 22)
        by = 608
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1)
        c.circle(bx, by, bubble_r, fill=0)
        
    # 2. Roll No Box & Grid
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#0D2B4E"))
    c.drawString(col0_x + 10, 575, "Roll No")
    
    # Draw 5 writing boxes
    box_y = 550
    box_w = 18
    for idx in range(5):
        bx = col0_x + (idx * box_w)
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1)
        c.rect(bx, box_y, box_w, box_w, fill=0)
        
        # Pre-print the digit character in the box if participant is provided
        if participant and len(participant.roll_number) == 5:
            digit_char = participant.roll_number[idx]
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(black)
            c.drawCentredString(bx + box_w/2, box_y + 4, digit_char)
            
    # Draw Roll No Bubble Grid (5 columns, 10 rows from 0 to 9)
    roll_start_y = 530
    for row_idx in range(10):
        ry = roll_start_y - (row_idx * 18)
        
        # Row label (0 to 9) on the left
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(HexColor("#555555"))
        c.drawString(col0_x - 12, ry - 3, str(row_idx))
        
        for col_idx in range(5):
            bx = col0_x + 9 + (col_idx * box_w)
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1)
            
            # Determine if this specific bubble should be filled in
            should_fill = False
            if participant and len(participant.roll_number) == 5:
                digit_val = int(participant.roll_number[col_idx])
                if row_idx == digit_val:
                    should_fill = True
            
            if should_fill:
                c.setFillColor(black)
                c.circle(bx, ry, bubble_r, fill=1, stroke=1)
            else:
                c.setFillColor(white)
                c.circle(bx, ry, bubble_r, fill=0, stroke=1)
                
    # 3. Group (Junior / Senior)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#0D2B4E"))
    c.drawString(col0_x, 330, "Group")
    
    c.setFont("Helvetica", 8)
    c.drawString(col0_x, 317, "Junior")
    c.drawString(col0_x + 35, 317, "Senior")
    
    # Draw Group Bubbles (Junior = idx 0, Senior = idx 1)
    for idx in range(2):
        bx = col0_x + 3 + (idx * 35)
        by = 303
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1)
        
        # Determine if this specific bubble should be filled in
        should_fill = False
        if participant:
            if idx == 0 and participant.group == 'JUNIOR':
                should_fill = True
            elif idx == 1 and participant.group == 'SENIOR':
                should_fill = True
                
        if should_fill:
            c.setFillColor(black)
            c.circle(bx, by, bubble_r, fill=1, stroke=1)
        else:
            c.setFillColor(white)
            c.circle(bx, by, bubble_r, fill=0, stroke=1)
            
    # Middle Column: Questions 1 - 25
    col1_x = 225
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(HexColor("#0D2B4E"))
    c.drawString(col1_x - 35, 635, "Section 1 (Q1-Q25)")
    
    # Column Headers A B C D
    c.setFont("Helvetica-Bold", 8)
    for idx, opt in enumerate(["A", "B", "C", "D"]):
        c.drawCentredString(col1_x + (idx * 22), 618, opt)
        
    # Right Column: Questions 26 - 50
    col2_x = 410
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(HexColor("#0D2B4E"))
    c.drawString(col2_x - 35, 635, "Section 2 (Q26-Q50)")
    
    # Column Headers A B C D
    c.setFont("Helvetica-Bold", 8)
    for idx, opt in enumerate(["A", "B", "C", "D"]):
        c.drawCentredString(col2_x + (idx * 22), 618, opt)
        
    # Helper to draw question rows in blocks of 5
    def draw_question_row(q_num, x, y):
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(HexColor("#0D2B4E"))
        c.drawString(x - 35, y - 3, f"{q_num:02d}")
        
        options = ["A", "B", "C", "D"]
        for idx, opt in enumerate(options):
            bx = x + (idx * 22)
            
            # Circle
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1)
            c.circle(bx, y, bubble_r, fill=0)
            
            # Letter
            c.setFont("Helvetica", 7)
            c.setFillColor(HexColor("#0D2B4E"))
            c.drawCentredString(bx, y - 2.5, opt)
            
    # Draw the 25 rows for both columns
    for r in range(25):
        y = get_row_y_coordinate(r)
        
        # Section 1 (Q1 - Q25)
        draw_question_row(r + 1, col1_x, y)
        
        # Section 2 (Q26 - Q50)
        draw_question_row(r + 26, col2_x, y)
        
    # Draw vertical separator lines between columns
    c.setStrokeColor(HexColor("#E2E8F0"))
    c.setLineWidth(1)
    c.line(195, 645, 195, 75)
    c.line(378, 645, 378, 75)
    
    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawCentredString(297, 25, "QuizMaster OMR System • Designed for Automated Grading")

def generate_blank_omr_pdf(filename):
    c = canvas.Canvas(filename, pagesize=A4)
    draw_omr_sheet_on_canvas(c, None)
    c.showPage()
    c.save()

def generate_personalized_omr_pdf(filename, participant):
    c = canvas.Canvas(filename, pagesize=A4)
    draw_omr_sheet_on_canvas(c, participant)
    c.showPage()
    c.save()

def generate_personalized_omr_sheets_pdf(filename, participants):
    c = canvas.Canvas(filename, pagesize=A4)
    for p in participants:
        draw_omr_sheet_on_canvas(c, p)
        c.showPage()
    c.save()

if __name__ == '__main__':
    generate_blank_omr_pdf("blank_omr_sheet.pdf")
