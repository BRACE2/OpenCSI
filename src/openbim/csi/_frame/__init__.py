#===----------------------------------------------------------------------===#
#
#         STAIRLab -- STructural Artificial Intelligence Laboratory
#
#===----------------------------------------------------------------------===#
#
import sys
import numpy as np

from ..utility import UnimplementedInstance, find_row


def _is_truss(frame, csi):
    if "FRAME RELEASE ASSIGNMENTS 1 - GENERAL" in csi:
        release = find_row(csi["FRAME RELEASE ASSIGNMENTS 1 - GENERAL"],
                        Frame=frame["Frame"])
    else:
        return False

    return release and all(release[i] for i in ("TI", "M2I", "M3I", "M2J", "M3J"))


def _orient(xi, xj, angle):
    """
    Calculate the coordinate transformation vector.
    xi is the location of node I, xj node J,
    and `angle` is the rotation about the local axis in degrees

    By default local axis 2 is always in the 1-Z plane, except if the object
    is vertical and then it is parallel to the global X axis.
    The definition of the local axes follows the right-hand rule.
    """

    # The local 1 axis points from node I to node J
    dx, dy, dz = e1 = xj - xi
    # Global z
    E3 = np.array([0, 0, 1])

    # In Sap2000, if the element is vertical, the local y-axis is the same as the
    # global x-axis, and the local z-axis can be obtained by cross-multiplying
    # the local x-axis with the local y-axis.
    if dx == 0 and dy == 0:
        e2 = np.array([1, 0, 0])

    # Otherwise, the plane composed of the local x-axis and the local
    # y-axis is a vertical plane. In this
    # case, the local z-axis can be obtained by the cross product of the local
    # x-axis and the global z-axis.
    else:
        e2 = np.cross(E3, e1)

    e3 = np.cross(e1, e2)

    # Rotate the local axis using the Rodrigue rotation formula
    # convert from degrees to radians
    angle = angle / 180 * np.pi
    e3r = e3 * np.cos(angle) + np.cross(e1, e3) * np.sin(angle)
    # Finally, the normalized local z-axis is returned
    return e3r / np.linalg.norm(e3r)


def create_frames(csi, model, library, config, conv):
    ndm = config.get("ndm", 3)
    log = []

    # itag = 1
    transform = 1

    tags = {}

    for frame in csi.get("CONNECTIVITY - FRAME",[]):
        if _is_truss(frame, csi):
            conv.log(UnimplementedInstance("Truss", frame))
            continue

        if "IsCurved" in frame and frame["IsCurved"]:
            conv.log(UnimplementedInstance("Frame.Curve", frame))

        nodes = (
            conv.identify("Joint", "node", frame["JointI"]),
            conv.identify("Joint", "node", frame["JointJ"])
        )

        if "FRAME ADDED MASS ASSIGNMENTS" in csi:
            row = find_row(csi["FRAME ADDED MASS ASSIGNMENTS"],
                            Frame=frame["Frame"])
            mass = row["MassPerLen"] if row else 0.0
        else:
            mass = 0.0

        #
        # Geometric transformation
        #
        if "FRAME LOCAL AXES ASSIGNMENTS 1 - TYPICAL" in csi:
            row = find_row(csi["FRAME LOCAL AXES ASSIGNMENTS 1 - TYPICAL"],
                            Frame=frame["Frame"])
            angle = row["Angle"] if row else 0.0
        else:
            angle = 0

        xi = np.array(model.nodeCoord(nodes[0]))
        xj = np.array(model.nodeCoord(nodes[1]))
        if np.linalg.norm(xj - xi) < 1e-10:
            log.append(UnimplementedInstance("Frame.ZeroLength", frame))
            print(f"ZERO LENGTH FRAME: {frame['Frame']}", file=sys.stderr)
            continue

        if ndm == 3:
            vecxz = _orient(xi, xj, angle)
            model.geomTransf("Linear", transform, *vecxz)
        else:
            model.geomTransf("Linear", transform)

        transform += 1

        #
        # Section
        #
        assign  = find_row(csi["FRAME SECTION ASSIGNMENTS"], Frame=frame["Frame"])

        # section = library["frame_sections"][assign["AnalSect"]] # conv.identify("AnalSect", "section", assign["AnalSect"]) #

        if ("SectionType" not in assign) or (assign["SectionType"] != "Nonprismatic") or \
           assign["NPSectType"] == "Advanced":
            
            section = conv.identify("AnalSect", "section", assign["AnalSect"])
            e = model.element("PrismFrame", None,
                          nodes,
                          section=section,
                          transform=transform-1,
                          mass=mass
            )
            tags[frame["Frame"]] = e


        elif assign["NPSectType"] == "Default":
            # Non-prismatic sections
            e = model.element("ForceFrame",
                              None,
                              nodes,
                              transform-1,
                              conv.identify("AnalSect", "integration", assign["AnalSect"]),
                              mass=mass
            )
            tags[frame["Frame"]] = e

        else:
            conv.log(UnimplementedInstance("FrameSection.NPSectType", assign["NPSectType"]))
            continue

    library["frame_tags"] = tags


    return log


